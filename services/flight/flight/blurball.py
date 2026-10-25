"""BlurBall on Apple MPS (D-30): a candidate source next to the classical detector. The tracker decides.

Adapted from the archived two-camera demo (`archive/tt-demo-failure-status`, `services/flight/flight/blurball.py`).
The network is upstream BlurBall @ 2f0f549 (MIT, vendored unmodified in `vendor/blurball`); upstream's runner is not
used, so its `device == "cuda"` assert never runs. The weights (license unstated, D-30: the user accepts using them,
we never redistribute them) live in an ignored local path, `$TROPHY_BLURBALL_WEIGHTS` or `<repo>/weights/blurball_best`,
and are pinned by SHA-256.

Fixes from CLAUDE.md Gotchas: frames are converted BGR -> RGB before the ImageNet normalisation (the loader trained on
PIL RGB); frames are deduplicated by `seq` (a repeated seq never enters the 3-frame window); a device fallback to the
CPU is never silent (`PYTORCH_ENABLE_MPS_FALLBACK=1` is refused, and `device` is reported in every heartbeat).

The model maps 3 consecutive frames to 3 heatmaps. `BlurBallDetector.push` buffers frames and runs once per
`stride` frames (stride 3: non-overlapping windows, one inference per 3 frames, two frames of extra latency), so it
returns candidates for zero or more earlier frames. Heatmap peaks are uncalibrated ranking scores, never
probabilities; every peak above `threshold` is a candidate and only the gated tracker turns them into a track (the
archived demo's ungated "largest mass" selection is what made the ball teleport).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

UPSTREAM_COMMIT = "2f0f5496f7ba4b5b1a36790749935121b2ce972d"
WEIGHT_SHA256 = "3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f"
REPO = Path(__file__).resolve().parents[3]
VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "blurball"
IN_W, IN_H = 512, 288
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def default_weights() -> Path:
    env = os.environ.get("TROPHY_BLURBALL_WEIGHTS")
    if env:
        return Path(env)
    for root in (REPO, REPO.parent / "trophy"):  # agent worktrees share the main checkout's ignored weights/
        p = root / "weights" / "blurball_best"
        if p.is_file():
            return p
    return REPO / "weights" / "blurball_best"


class _Cfg(dict):
    """Upstream mixes dict and attribute access on its Hydra config."""

    __getattr__ = dict.__getitem__


def _cfg(v):
    if isinstance(v, dict):
        return _Cfg({k: _cfg(x) for k, x in v.items()})
    if isinstance(v, list):
        return [_cfg(x) for x in v]
    return v


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def letterbox(w: int, h: int) -> np.ndarray:
    """Full-image letterbox into the model input (2x3 affine); 16:9 frames fill it exactly."""
    s = min(IN_W / w, IN_H / h)
    return np.array([[s, 0, (IN_W - w * s) / 2], [0, s, (IN_H - h * s) / 2]], np.float32)


def preprocess(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """BGR frame -> (3, 288, 512) normalised RGB tensor data, and the inverse affine back to frame pixels."""
    h, w = bgr.shape[:2]
    m = letterbox(w, h)
    rgb = cv2.cvtColor(cv2.warpAffine(bgr, m, (IN_W, IN_H), flags=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
    x = (rgb.astype(np.float32) / 255.0 - _MEAN) / _STD
    return np.ascontiguousarray(x.transpose(2, 0, 1)), cv2.invertAffineTransform(m)


def peaks(hm: np.ndarray, inverse: np.ndarray, w: int, h: int, threshold: float, k: int) -> list[dict]:
    """Connected components above `threshold` -> candidates in frame pixels, best first.

    `score` is the component's peak heatmap value (an uncalibrated ranking score); `L_px`/`theta_deg` are the blur
    streak's full length and direction from the component's principal axis (upstream reports half the length).
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats((hm > threshold).astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x0, y0, bw, bh, _ = stats[i]
        sub = labels[y0 : y0 + bh, x0 : x0 + bw] == i
        ys, xs = np.nonzero(sub)
        wts = hm[y0 : y0 + bh, x0 : x0 + bw][sub]
        mass = float(wts.sum())
        cx, cy = float(np.dot(xs, wts) / mass) + x0, float(np.dot(ys, wts) / mass) + y0
        u, v = inverse @ np.array([cx, cy, 1.0])
        if not (0 <= u < w and 0 <= v < h):
            continue  # never clamp a padding response onto the image border
        cand = {"xy_px": [float(u), float(v)], "score": float(wts.max()), "mass": mass}
        if len(xs) > 2:
            pts = np.column_stack((xs, ys)).astype(np.float32)
            mean, axes = cv2.PCACompute(pts, mean=None)
            ext = float(np.ptp((pts - mean) @ axes[0]))
            vec = inverse[:, :2] @ (axes[0] * ext)
            cand["L_px"] = float(np.hypot(*vec))
            cand["theta_deg"] = float(np.degrees(np.arctan2(vec[1], vec[0])))
        out.append(cand)
    out.sort(key=lambda c: -c["score"])
    return out[:k]


class Predictor:
    """The network on one device. `device="auto"` picks MPS when available and says so; it never falls back quietly."""

    def __init__(self, weights: str | Path | None = None, device: str = "auto") -> None:
        import torch
        import yaml

        if device not in ("auto", "mps", "cpu"):
            raise ValueError("device must be auto, mps or cpu")
        if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
            raise RuntimeError("unset PYTORCH_ENABLE_MPS_FALLBACK: a silent per-op CPU fallback is not allowed")
        mps = torch.backends.mps.is_available()
        self.device = ("mps" if mps else "cpu") if device == "auto" else device
        if self.device == "mps" and not mps:
            raise RuntimeError("MPS unavailable: run natively on Apple Silicon, or pass device='cpu' explicitly")
        path = Path(weights) if weights else default_weights()
        if not path.is_file():
            raise FileNotFoundError(f"BlurBall weights not found at {path} (set TROPHY_BLURBALL_WEIGHTS)")
        self.weights_sha256 = sha256(path)
        if self.weights_sha256 != WEIGHT_SHA256:
            raise ValueError(f"{path}: checksum differs from the pinned BlurBall weights")
        spec = importlib.util.spec_from_file_location("trophy_vendor_blurball", VENDOR / "src/models/blurball.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg = _cfg(yaml.safe_load((VENDOR / "src/configs/model/blurball.yaml").read_text()))
        self.model = mod.BlurBall(cfg)
        # The official file is a checkpoint dict with model_state_dict, so weights_only=True loads it (no pickle code).
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(ckpt["model_state_dict"], strict=True)
        self.model.eval().to(self.device)
        self.torch = torch
        self.torch_version = torch.__version__

    def _sync(self) -> None:
        if self.device == "mps":
            self.torch.mps.synchronize()

    def __call__(self, chw: list[np.ndarray]) -> tuple[np.ndarray, float]:
        """Three chronological (3, H, W) inputs -> three (H, W) sigmoid heatmaps, and the model time in ms."""
        torch = self.torch
        x = torch.from_numpy(np.concatenate(chw, axis=0)[None]).to(self.device)
        t0 = time.perf_counter()
        with torch.inference_mode():
            y = self.model(x)[0].sigmoid()
        hm = y.cpu().numpy()[0]  # the copy synchronises the device
        return hm, (time.perf_counter() - t0) * 1000


@dataclass
class _Buffered:
    seq: int
    t_s: float
    chw: np.ndarray
    inverse: np.ndarray
    w: int
    h: int


@dataclass
class BlurBallDetector:
    """Feeds consecutive frames to the network in windows of 3 and returns per-frame candidates."""

    predictor: Predictor
    threshold: float = 0.5
    max_candidates: int = 5
    stride: int = 3  # 3: non-overlapping windows; 1: every frame is the newest of a sliding window (3x the cost)
    # "rgb" for the white ball it was trained on (D-10); "maxgray" (max over channels, replicated) is the archived
    # demo's adaptation for an orange ball, which reads as near-white in that channel
    photometric: str = "rgb"
    _buf: list[_Buffered] = field(default_factory=list)
    _since: int = 0
    last_seq: int | None = None
    model_ms: float = 0.0  # EWMA
    runs: int = 0

    @property
    def device(self) -> str:
        return self.predictor.device

    def reset(self) -> None:
        self._buf.clear()
        self._since = 0
        self.last_seq = None

    def push(self, seq: int, t_s: float, bgr: np.ndarray) -> list[dict]:
        """Add one frame. Returns [{"frame": seq, "t_s", "candidates": [...]}] for the frames this call resolved."""
        if seq == self.last_seq:
            return []  # dedupe by seq
        if self.last_seq is not None and seq != self.last_seq + 1:
            self.reset()  # a gap: the window must be consecutive frames
        self.last_seq = seq
        if self.photometric == "maxgray":
            bgr = cv2.merge([bgr.max(axis=2)] * 3)
        chw, inv = preprocess(bgr)
        self._buf.append(_Buffered(seq, t_s, chw, inv, bgr.shape[1], bgr.shape[0]))
        self._buf = self._buf[-3:]
        self._since += 1
        if len(self._buf) < 3 or self._since < self.stride:
            return []
        self._since = 0
        hm, ms = self.predictor([b.chw for b in self._buf])
        self.model_ms = ms if self.runs == 0 else 0.9 * self.model_ms + 0.1 * ms
        self.runs += 1
        frames = self._buf if self.stride >= 3 else self._buf[-self.stride :]
        first = len(self._buf) - len(frames)
        return [
            {
                "frame": b.seq,
                "t_s": b.t_s,
                "candidates": peaks(hm[first + i], b.inverse, b.w, b.h, self.threshold, self.max_candidates),
            }
            for i, b in enumerate(frames)
        ]

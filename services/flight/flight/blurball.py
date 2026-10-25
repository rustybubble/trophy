"""BlurBall, the pretrained ball detector, through Mu Du's validated adapter (spikes/serve-analysis/trophy/model.py).

The adapter loads the unmodified upstream architecture (vendor/blurball @ 2f0f549), checks the official checkpoint's
SHA-256, and fixes upstream's BGR/RGB, preprocessing and decoding issues (PROVENANCE.md). It is loaded here by file
path under its own module name, because its package is also called `trophy` and would shadow py-trophy.

    model = load()                      # MPS when available (no silent CPU fallback), the pinned weights
    det = model.detect([rgb0, rgb1, rgb2])   # three consecutive RGB frames -> one best detection per frame (or None)

fp16 is the MPS default (see `load`). A window yields a heatmap for each of its three frames. Live, windows step
by `stride` frames: stride 3 gives every
frame exactly one prediction for a third of stride 1's GPU time (measured on this M5 on a real 720p clip: 107 vs 109
of 120 frames detected, positions within 2.0 px at p95). Scores are the component's peak probability: uncalibrated.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / "spikes" / "serve-analysis" / "trophy" / "model.py"
WEIGHTS = ROOT / "spikes" / "serve-analysis" / "weights" / "blurball_best"


@dataclass
class Detection:
    x: float
    y: float
    score: float  # component peak probability (uncalibrated)
    mass: float  # upstream's ranking: the component's probability sum
    blur_len_px: float
    blur_angle_deg: float


def _adapter():
    if "flight_blurball_adapter" in sys.modules:
        return sys.modules["flight_blurball_adapter"]
    if not ADAPTER.is_file():
        raise FileNotFoundError(f"BlurBall adapter missing: {ADAPTER} (merge codex/serve-legality-demo)")
    spec = importlib.util.spec_from_file_location("flight_blurball_adapter", ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["flight_blurball_adapter"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class BlurBall:
    def __init__(self, device: str = "auto", weights: Path = WEIGHTS, threshold: float = 0.7, half: bool = False):
        if not Path(weights).is_file():
            raise FileNotFoundError(
                f"BlurBall weights missing: {weights}. Run `cd spikes/serve-analysis && bash scripts/bootstrap.sh`."
            )
        self.ad = _adapter()
        self.pred = self.ad.Predictor(weights=weights, device=device)
        self.device = self.pred.device
        self.threshold = threshold
        self.half = bool(half and self.device == "mps")
        if self.half:
            self.pred.model = self.pred.model.half()
        self.calls = 0
        self.model_ms = 0.0

    def preprocess(self, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.ad.preprocess(rgb)

    def heatmaps(self, chw: list[np.ndarray]) -> np.ndarray:
        import torch

        x = torch.from_numpy(np.concatenate(chw, axis=0)[None]).to(self.device)
        if self.half:
            x = x.half()
        t = time.perf_counter()
        with torch.inference_mode():
            y = self.pred.model(x)[0].sigmoid()
        hm = y.float().cpu().numpy()[0]
        self.model_ms += (time.perf_counter() - t) * 1000
        self.calls += 1
        return hm

    def decode(self, hm: np.ndarray, inverse: np.ndarray, w: int, h: int) -> Detection | None:
        cands, _peak = self.ad.decode_heatmap(hm, inverse, w, h, self.threshold)
        if not cands:
            return None
        b = max(cands, key=lambda c: c["component_mass"])  # upstream's selection
        return Detection(b["x"], b["y"], b["score"], b["component_mass"], b["blur_length_px"], b["blur_angle_degrees"])

    def detect(self, rgbs: list[np.ndarray]) -> list[Detection | None]:
        h, w = rgbs[0].shape[:2]
        pre = [self.preprocess(f) for f in rgbs]
        hm = self.heatmaps([p[0] for p in pre])
        return [self.decode(hm[i], pre[i][1], w, h) for i in range(3)]

    def warmup(self, rgb: np.ndarray) -> float:
        t = time.perf_counter()
        self.detect([rgb, rgb, rgb])
        return (time.perf_counter() - t) * 1000


def load(device: str | None = None, half: bool | None = None) -> BlurBall:
    """fp16 on MPS by default: on 600 frames of the team's real clip it found the ball in exactly the same 532 frames
    as fp32, positions within 0.57 px (max), at 40 vs 57 ms per window, which is what lets two cameras run live on an
    M5. BLURBALL_FP32=1 (or half=False) keeps Mu's validated fp32 path."""
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        raise RuntimeError("unset PYTORCH_ENABLE_MPS_FALLBACK: a silent CPU fallback is not allowed")
    if half is None:
        half = os.environ.get("BLURBALL_FP32", "0") != "1"
    return BlurBall(device=device or os.environ.get("BLURBALL_DEVICE", "auto"), half=half)

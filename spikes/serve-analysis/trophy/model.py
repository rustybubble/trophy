"""Small native-device adapter; vendored model source is never modified."""
import hashlib
import importlib.util
import os
from pathlib import Path
import time

import cv2
import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = '2f0f5496f7ba4b5b1a36790749935121b2ce972d'
WEIGHT_SHA256 = '3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f'
DEFAULT_WEIGHTS = ROOT / 'weights/blurball_best'
WIDTH, HEIGHT = 512, 288


class ModelConfig(dict):
    """The upstream model mixes dictionary and Hydra attribute access."""
    __getattr__ = dict.__getitem__


def model_config(value):
    if isinstance(value, dict):
        return ModelConfig({key: model_config(item) for key, item in value.items()})
    if isinstance(value, list):
        return [model_config(item) for item in value]
    return value


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geometry(width, height):
    """Full-image letterbox; agrees with upstream affine for 16:9 footage."""
    scale = min(WIDTH / width, HEIGHT / height)
    return np.array([[scale, 0, (WIDTH - width * scale) / 2],
                     [0, scale, (HEIGHT - height * scale) / 2]], dtype=np.float32)


def preprocess(rgb):
    h, w = rgb.shape[:2]
    mat = geometry(w, h)
    resized = cv2.warpAffine(rgb, mat, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR)
    # PIL RGB -> ToTensor -> ImageNet normalization in the training loader.
    x = resized.astype(np.float32) / 255.0
    x = (x - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)
    return np.ascontiguousarray(x.transpose(2, 0, 1)), cv2.invertAffineTransform(mat)


def decode_heatmap(hm, inverse, width, height, threshold):
    """Upstream connected components, weighted center and mass ranking.

    score is component peak probability, mass is upstream's uncalibrated sum.
    Blur extent is PCA full length (upstream reports half length).
    """
    peak = float(hm.max())
    count, labels = cv2.connectedComponents((hm > threshold).astype(np.uint8))
    candidates = []
    for label in range(1, count):
        ys, xs = np.where(labels == label)
        weights = hm[ys, xs]
        mass = float(weights.sum())
        center = np.array([np.dot(xs, weights) / mass, np.dot(ys, weights) / mass])
        xy = inverse @ np.r_[center, 1.0]
        if not (0 <= xy[0] < width and 0 <= xy[1] < height):
            continue  # Never clamp a padding detection onto the image border.
        coords = np.column_stack((xs, ys)).astype(np.float32)
        if len(coords) > 1:
            mean, axes = cv2.PCACompute(coords, mean=None)
            axis = axes[0]
            projections = (coords - mean) @ axis
            extent = float(np.ptp(projections))
            vector = inverse[:, :2] @ (axis * extent)
            angle = float(np.degrees(np.arctan2(vector[1], vector[0])))
            length = float(np.linalg.norm(vector))
        else:
            angle, length = 0.0, 0.0
        candidates.append(dict(x=float(xy[0]), y=float(xy[1]), score=float(weights.max()),
                               component_mass=mass, blur_angle_degrees=angle,
                               blur_length_px=length))
    return candidates, peak


class Predictor:
    def __init__(self, weights=DEFAULT_WEIGHTS, device='auto'):
        if device not in ('auto', 'mps', 'cpu'):
            raise ValueError('device must be auto, mps or cpu')
        if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') == '1':
            raise RuntimeError('Unset PYTORCH_ENABLE_MPS_FALLBACK: silent model CPU fallback is disallowed.')
        self.requested_device = device
        available = torch.backends.mps.is_available()
        self.device = 'mps' if device == 'auto' and available else ('cpu' if device == 'auto' else device)
        if self.device == 'mps' and not available:
            raise RuntimeError('MPS unavailable. Run natively on Apple Silicon or choose --device cpu.')
        path = Path(weights)
        if not path.is_file():
            raise FileNotFoundError(f'Weights unavailable: {path}. Run python scripts/setup_assets.py.')
        self.weight_sha256 = sha256(path)
        if self.weight_sha256 != WEIGHT_SHA256:
            raise ValueError('Checkpoint checksum differs from the pinned official BlurBall weights.')
        upstream = ROOT / 'vendor/blurball'
        mod = load_source('trophy_upstream_blurball', upstream / 'src/models/blurball.py')
        cfg = model_config(yaml.safe_load((upstream / 'src/configs/model/blurball.yaml').read_text()))
        self.model = mod.BlurBall(cfg)
        # Official file is a checkpoint dict containing model_state_dict (not TorchScript).
        ckpt = torch.load(path, map_location='cpu', weights_only=True)
        self.model.load_state_dict(ckpt['model_state_dict'], strict=True)
        self.model.eval().to(self.device)
        self.checkpoint_keys = list(ckpt)
        self.warmup_ms = None

    def sync(self):
        if self.device == 'mps':
            torch.mps.synchronize()

    def predict(self, frames):
        """Three chronological CHW frames -> three same-order sigmoid heatmaps."""
        x = torch.from_numpy(np.concatenate(frames, axis=0)[None]).to(self.device)
        self.sync()
        start = time.perf_counter()
        with torch.inference_mode():
            y = self.model(x)[0].sigmoid()
        self.sync()
        model_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        hm = y.cpu().numpy()[0]
        transfer_ms = (time.perf_counter() - start) * 1000
        return hm, model_ms, transfer_ms

    def warmup(self, frames):
        _, self.warmup_ms, _ = self.predict(frames)

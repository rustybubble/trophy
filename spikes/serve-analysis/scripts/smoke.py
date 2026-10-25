"""Real footage, strict official checkpoint, full-resolution model smoke test."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from trophy.model import Predictor, preprocess, decode_heatmap

p = argparse.ArgumentParser()
p.add_argument('--device', default='mps', choices=['mps', 'cpu', 'auto'])
p.add_argument('--video', default='samples/official-00-001.mp4')
a = p.parse_args()
cap = cv2.VideoCapture(a.video)
frames = []
for _ in range(3):
    ok, bgr = cap.read()
    if not ok:
        raise RuntimeError('Need three real frames for model smoke test')
    h, w = bgr.shape[:2]
    image, inverse = preprocess(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    frames.append(image)
cap.release()
m = Predictor(device=a.device)
m.warmup(frames)
hm, latency, transfer = m.predict(frames)
assert hm.shape == (3, 288, 512) and np.isfinite(hm).all()
result = dict(device=m.device, shape=hm.shape, model_ms=latency, output_transfer_ms=transfer,
              warmup_ms=m.warmup_ms, checkpoint_keys=m.checkpoint_keys,
              predictions=[decode_heatmap(x, inverse, w, h, .7) for x in hm])
print(json.dumps(result, indent=2))

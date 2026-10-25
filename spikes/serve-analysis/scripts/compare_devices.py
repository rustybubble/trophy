"""CPU/MPS heatmaps and detections from identical real temporal windows."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import torch
from trophy.model import Predictor, preprocess, decode_heatmap

p = argparse.ArgumentParser()
p.add_argument('video')
p.add_argument('--output', required=True)
p.add_argument('--starts', default='0,30,60')
a = p.parse_args()
if not torch.backends.mps.is_available():
    raise RuntimeError('MPS unavailable; no comparison claimed')
cpu, mps = Predictor(device='cpu'), Predictor(device='mps')
cap = cv2.VideoCapture(a.video)
results = []
for start in map(int, a.starts.split(',')):
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    for _ in range(3):
        ok, bgr = cap.read()
        if not ok:
            break
        h, w = bgr.shape[:2]
        x, inv = preprocess(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        frames.append(x)
    if len(frames) < 3:
        continue
    if cpu.warmup_ms is None:
        cpu.warmup(frames)
        mps.warmup(frames)
    chm, cms, _ = cpu.predict(frames)
    mhm, mms, _ = mps.predict(frames)
    item = dict(start=start, cpu_model_ms=cms, mps_model_ms=mms,
                max_heatmap_abs_difference=float(np.max(np.abs(chm - mhm))),
                mean_heatmap_abs_difference=float(np.mean(np.abs(chm - mhm))), heads=[])
    for head in range(3):
        cc, _ = decode_heatmap(chm[head], inv, w, h, .7)
        mc, _ = decode_heatmap(mhm[head], inv, w, h, .7)
        cb = max(cc, key=lambda x: x['component_mass']) if cc else None
        mb = max(mc, key=lambda x: x['component_mass']) if mc else None
        item['heads'].append(dict(frame_index=start + head, cpu=cb, mps=mb,
                                  detection_agrees=bool(cb) == bool(mb),
                                  position_difference_px=float(np.hypot(cb['x'] - mb['x'], cb['y'] - mb['y'])) if cb and mb else None))
    results.append(item)
cap.release()
if not results:
    raise RuntimeError('No real temporal windows compared')
Path(a.output).write_text(json.dumps(dict(torch=torch.__version__, windows=results), indent=2))
print(json.dumps(results, indent=2))

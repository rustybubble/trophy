"""Compare actual CPU and MPS model outputs after the new color preprocessing."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,numpy as np
from trophy.model import Predictor,preprocess
cpu=Predictor(device='cpu');mps=Predictor(device='mps');rows=[]
for view in ['side','oblique']:
 cap=cv2.VideoCapture(f'samples/tt3d/game_00/{view}-010.mp4')
 for frame in [30,100,220]:
  cap.set(cv2.CAP_PROP_POS_FRAMES,frame-1);xx=[]
  for _ in range(3):
   ok,bgr=cap.read()
   if not ok:raise ValueError('Probe frame missing')
   gray=bgr.max(axis=2);rgb=np.repeat(gray[...,None],3,axis=2);xx.append(preprocess(rgb)[0])
  a,cpu_ms,_=cpu.predict(xx);b,mps_ms,_=mps.predict(xx)
  peaks_a=a.reshape(3,-1).argmax(axis=1);peaks_b=b.reshape(3,-1).argmax(axis=1)
  rows.append(dict(view=view,center_frame=frame,max_heatmap_absolute_delta=float(np.max(np.abs(a-b))),
     mean_heatmap_absolute_delta=float(np.mean(np.abs(a-b))),heatmap_argmax_equal=bool(np.array_equal(peaks_a,peaks_b)),
     cpu_ms=cpu_ms,mps_ms=mps_ms))
 cap.release()
report=dict(photometric='max-channel-gray',windows=rows,all_argmax_equal=all(r['heatmap_argmax_equal'] for r in rows),
 max_heatmap_absolute_delta=max(r['max_heatmap_absolute_delta'] for r in rows),mps_fallback_enabled=False)
Path('artifacts/multiview/device-comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

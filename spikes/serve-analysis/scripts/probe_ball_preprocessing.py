"""Exploratory photometric robustness probe; never supplies reference positions."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,json,numpy as np
from trophy.model import Predictor,preprocess,decode_heatmap
p=Predictor(device='mps');cap=cv2.VideoCapture('samples/tt3d/game_00/side-010.mp4');out=[]
for i in [30,70,100,140,180,220]:
 cap.set(1,i-1);frames=[cap.read()[1] for _ in range(3)];row={'frame':i}
 for mode in ['original','gray','orange_neutralized']:
  xx=[]
  for bgr in frames:
   rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
   if mode=='gray':rgb=np.repeat(np.max(rgb,axis=2)[...,None],3,axis=2)
   if mode=='orange_neutralized':
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV);m=(hsv[:,:,0]<30)&(hsv[:,:,1]>100)&(hsv[:,:,2]>130)
    rgb[m]=np.max(rgb,axis=2)[m,None]
   x,inv=preprocess(rgb);xx.append(x)
  h,ms,_=p.predict(xx);cand,peak=decode_heatmap(h[1],inv,1920,1080,.5)
  row[mode]=sorted(cand,key=lambda c:c['component_mass'],reverse=True)[:3]
 out.append(row)
print(json.dumps(out,indent=2));Path('artifacts/multiview/photometric-probe.json').write_text(json.dumps(out,indent=2))

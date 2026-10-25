"""Official RacketVision TrackNetV3 smoke test, with corrected training alignment.

The training loader is BGR [0,1], median + four frames ending at the target.
Upstream inference.py incorrectly ends its window one frame before the target;
we follow the training loader instead. No model source modifications.
"""
import sys,json,hashlib,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/racketvision/source/BallTrack'))
import cv2,numpy as np,torch
from model.tracknet_v3 import TrackNet
p=Path('weights/racketvision_balltrack.pth')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='00d707b9db7a49561c411e4765956e79bcd7c7e20c7a0a535073440b3e972342'
# Official checkpoint includes trusted mmengine training metadata, not just tensors.
s=torch.load(p,map_location='cpu',weights_only=False)['state_dict'];s={k.removeprefix('module.'):v for k,v in s.items()}
m=TrackNet(in_dim=15,out_dim=4,d_model=s['down_block_1.conv_1.conv.weight'].shape[0],last_only=True).eval().to('mps');m.load_state_dict(s,strict=True)
c=cv2.VideoCapture('samples/tt3d/game_00/side-010.mp4');frames=[]
while True:
 ok,f=c.read()
 if not ok:break
 frames.append(cv2.resize(f,(512,288)))
median=np.median(frames[::5],axis=0).astype(np.float32)/255;rows=[]
for i in [30,70,100,140,180,220]:
 x=np.concatenate([median]+[frames[j].astype(np.float32)/255 for j in range(i-3,i+1)],axis=2).reshape(288,512,5,3).transpose(2,3,0,1).reshape(15,288,512)
 # Concatenate image channels frame-by-frame, median first.
 torch.mps.synchronize();t=time.perf_counter()
 with torch.inference_mode():hm=m._forward(torch.from_numpy(x.copy())[None].to('mps'))[0,-1].cpu().numpy()
 torch.mps.synchronize();_,_,_,loc=cv2.minMaxLoc(hm);rows.append(dict(frame=i,x=loc[0]*3.75,y=loc[1]*3.75,peak=float(hm.max()),ms=(time.perf_counter()-t)*1000))
print(json.dumps(rows,indent=2));Path('artifacts/multiview/tracknet-probe.json').write_text(json.dumps(rows,indent=2))

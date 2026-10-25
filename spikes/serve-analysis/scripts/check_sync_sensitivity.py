"""Measure timing perturbations against the held-out reference with clock fixed."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from trophy.replay.multiview import load_camera,reconstruct_ball

cameras=[load_camera(f'samples/tt3d/game_00/{v}.yaml') for v in ['side','oblique']]
reports=[]
for name,prefix,ball_path,accuracy_path in [
 ('010','gray','ball-3d.json','demo/accuracy.json'),
 ('038','rally038','rally038-ball-3d.json','rally038-accuracy.json')]:
 a=json.loads(Path(f'artifacts/multiview/{prefix}-side/detections.json').read_text())
 b=json.loads(Path(f'artifacts/multiview/{prefix}-oblique/detections.json').read_text())
 baseline=json.loads(Path(f'artifacts/multiview/{ball_path}').read_text());offset=baseline['offset']
 reference=json.loads(Path(f'artifacts/multiview/{accuracy_path}').read_text())
 for error in [0,.005,.010,.020,-offset]:
  predicted,_=reconstruct_ball(a,b,cameras,offset+error);es=[];n=0
  for frame,p in zip(reference['frames'],predicted):
   if frame['partition']!='held_out' or not frame['reference_available']:continue
   n+=1
   if p.get('raw_world_position_m') is not None:es.append(np.linalg.norm(np.array(p['raw_world_position_m'])-frame['reference_position_m']))
  reports.append(dict(rally=name,applied_camera_offset_seconds=offset+error,perturbation_seconds=error,
      reference_frames=n,valid_frames=len(es),median_error_cm=float(np.median(es)*100) if es else None,
      p95_error_cm=float(np.percentile(es,95)*100) if es else None))
Path('artifacts/multiview/sync-sensitivity.json').write_text(json.dumps(dict(reference_clock_refitted=False,experiments=reports),indent=2))
print(json.dumps(reports,indent=2))

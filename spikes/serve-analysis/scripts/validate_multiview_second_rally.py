"""Run the frozen ball geometry on a second real rally, without reference input."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trophy.replay.multiview import load_camera,synchronize_ball,reconstruct_ball
from scripts.evaluate_multiview import evaluate

a=json.loads(Path('artifacts/multiview/rally038-side/detections.json').read_text())
b=json.loads(Path('artifacts/multiview/rally038-oblique/detections.json').read_text())
c=[load_camera(f'samples/tt3d/game_00/{v}.yaml') for v in ['side','oblique']]
offset,sync=synchronize_ball(a,b,c,initial=0)
ball,report=reconstruct_ball(a,b,c,offset)
path=Path('artifacts/multiview/rally038-ball-3d.json')
path.write_text(json.dumps(dict(ball=ball,report=report,offset=offset,sync=sync)))
evaluate(path,'artifacts/multiview/rally038-side/detections.json',
         'samples/tt3d/game_00/038/reference.csv','samples/tt3d/game_00/side.yaml',
         'artifacts/multiview/rally038-accuracy.json')

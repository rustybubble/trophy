"""Update player smoothing/mesh presentation without rerunning or changing tracking."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trophy.replay.motion import smooth_player_motion

ROOT=Path(__file__).resolve().parents[1]


def update(directory):
    root=Path(directory);path=root/'scene.json';scene=json.loads(path.read_text())
    baseline=json.dumps([dict(ball=f['ball'],players=[p['joints'] for p in f['players']]) for f in scene['frames']],sort_keys=True)
    report=smooth_player_motion(scene['frames'],scene['fps'])
    scene['continuous_avatars']=True;scene['report']['player_render_motion']=report
    unchanged=json.dumps([dict(ball=f['ball'],players=[p['joints'] for p in f['players']]) for f in scene['frames']],sort_keys=True)
    assert baseline==unchanged,'Presentation update altered measured tracking'
    report['tracking_unchanged_sha256']=hashlib.sha256(baseline.encode()).hexdigest()
    report['body_surface']='one connected watertight mesh, smoothly weighted across 15 bones'
    path.write_text(json.dumps(scene,separators=(',',':'),allow_nan=False))
    (root/'reconstruction-report.json').write_text(json.dumps(scene['report'],indent=2,allow_nan=False))
    for src in (ROOT/'web/multiview').iterdir():
        if src.is_file():shutil.copy2(src,root/src.name)
    (root/'motion-smoothing-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',default='artifacts/multiview/demo');a=p.parse_args();update(a.directory)

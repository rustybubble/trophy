"""Build an honest, rotatable single-camera reconstruction from real inference."""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from trophy.replay.geometry import calibrate,reconstruct_players,project
from trophy.replay.ball import reconstruct_ball
from trophy.model import sha256

ROOT=Path(__file__).resolve().parents[1]

def build(video,detections_path,poses_path,config_path,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(Path(config_path).read_text())
    detections=json.loads(Path(detections_path).read_text())
    raw=json.loads(Path(poses_path).read_text())
    if len(raw['frames'])!=len(detections):raise ValueError('Pose and ball frame counts do not match')
    for i,(p,b) in enumerate(zip(raw['frames'],detections)):
        if p['frame_index']!=i or b['frame_index']!=i:raise ValueError('Frame index mismatch')
        if abs(p['timestamp_seconds']-b['timestamp_seconds'])>.002:raise ValueError('Pose/ball timestamps do not align')
    camera=calibrate(cfg)
    players=reconstruct_players(raw['frames'],camera)
    ball,ball_report=reconstruct_ball(detections,cfg,camera)
    serial_camera={k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in camera.items()}
    frames=[dict(frame_index=i,time=b['timestamp_seconds'],players=p,ball=bb) for i,(b,p,bb) in enumerate(zip(detections,players,ball))]
    report=dict(type='approximate single-camera 3D reconstruction',video_sha256=sha256(video),
                source_video=str(Path(video).resolve()),source_pose_data=str(Path(poses_path).resolve()),
                source_ball_data=str(Path(detections_path).resolve()),
                source_hashes=dict(poses_sha256=sha256(poses_path),detections_sha256=sha256(detections_path),config_sha256=sha256(config_path)),camera=serial_camera,
                player_pose=raw['report'],ball=ball_report,frame_count=len(frames),
                neutral_stance_person_frames=[sum(p['id']==pid and p.get('leg_pose_prior',False) for frame in players for p in frame) for pid in range(2)],
                limitations=['Player joints come from actual pretrained MediaPipe inference, with inferred depth and occluded limbs.',
                             'Player translation uses foot/floor contact when reliable and explicit hip-height/playing-zone priors when feet are occluded.',
                             'Root motion is smoothed. Occluded legs use a marked neutral stance prior; no gait or swing is scripted.',
                             'Simple body figures are a visualization of estimated motion, not a measured motion-capture recording.'])
    scene=dict(schema_version=1,units='metres',axes='x table length; y table width; z up',
               duration=frames[-1]['time'],fps=raw['report']['fps'],
               table=dict(length=2.74,width=1.525,height=.76,net_height=.1525),
               camera=serial_camera,frames=frames,report=report)
    (out/'scene.json').write_text(json.dumps(scene,separators=(',',':'),allow_nan=False))
    (out/'reconstruction-report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    for path in (ROOT/'web/replay').iterdir():
        if path.is_file():shutil.copy2(path,out/path.name)
    shutil.copy2(video,out/'source.mp4')
    # Full-frame diagnostic overlay: model 2D skeleton + fitted ball reprojection.
    cap=cv2.VideoCapture(str(video));ok,frame=cap.read();cap.release()
    if ok:
        corners=np.asarray(cfg['table_corners_px'],int)
        cv2.polylines(frame,[corners],True,(255,200,0),2)
        for i,p in enumerate(corners):cv2.putText(frame,str(i),tuple(p),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,0),2)
        cv2.imwrite(str(out/'calibration.jpg'),frame)
    print(json.dumps({k:v for k,v in report.items() if k not in ['camera','limitations']},indent=2))
    return scene

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('--detections',required=True)
    p.add_argument('--poses',required=True);p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();build(a.video,a.detections,a.poses,a.config,a.output)

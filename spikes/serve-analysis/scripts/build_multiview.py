"""Build a two-camera rally replay from actual per-camera model predictions.

Reference 3D files are deliberately not accepted by this reconstruction command.
"""
import argparse,csv,json,shutil,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from trophy.model import sha256
from trophy.replay.motion import smooth_player_motion
from trophy.replay.multiview import (load_camera,pose_array,pose_world_array,
    reconstruct_poses,reconstruct_ball,synchronize_ball,synchronize_poses,viewer_coordinates)

ROOT=Path(__file__).resolve().parents[1]


def build(config_path,output):
    start=time.perf_counter();cfg=json.loads(Path(config_path).read_text());views=cfg['views']
    if len(views)!=2:raise ValueError('This tested implementation currently requires exactly two calibrated views')
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    cameras=[load_camera(v['calibration'],v.get('width',1920),v.get('height',1080)) for v in views]
    aa=[json.loads(Path(v['detections']).read_text()) for v in views]
    poses=[pose_array(v['poses']) for v in views]
    for detections,(ts,_,_) in zip(aa,poses):
        if len(detections)!=len(ts):raise ValueError('Pose and ball frame counts differ')
        if any(abs(r['timestamp_seconds']-t)>.002 for r,t in zip(detections,ts)):raise ValueError('Pose and ball timestamps differ')
    ta,a,ra=poses[0];tb,b,rb=poses[1]
    initial,pose_sync=synchronize_poses(ta,a,tb,b,cameras)
    offset,ball_sync=synchronize_ball(*aa,cameras,initial=initial)
    ball,ball_report=reconstruct_ball(*aa,cameras,offset,max_error=cfg.get('max_reprojection_error_px',8.))
    players,pose_report=reconstruct_poses(ta,a,tb,b,cameras,offset,world_b=pose_world_array(views[1]['poses']))
    frames=[dict(frame_index=i,time=float(t),players=p,ball=q) for i,(t,p,q) in enumerate(zip(ta,players,ball))]
    motion_report=smooth_player_motion(frames,ra['fps'])
    serial_cameras=[{k:v.tolist() for k,v in c.items()} for c in cameras]
    reports=[json.loads(Path(v['detections']).with_name('report.json').read_text()) for v in views]
    report=dict(type='two-camera calibrated reconstruction from real pretrained model detections',
        ball=ball_report,player_pose=pose_report,pose_inference=[ra,rb],ball_inference=reports,
        synchronization=dict(pose=pose_sync,ball=ball_sync),cameras=serial_cameras,
        source_hashes=[{k:dict(path=str(Path(v[k]).resolve()),sha256=sha256(v[k])) for k in ['video','calibration','detections','poses']} for v in views],
        frame_count=len(frames),duration_seconds=float(ta[-1]),
        player_render_motion=motion_report,
        reconstruction_seconds=time.perf_counter()-start,
        reference_3d_used_for_reconstruction=False,
        racket=dict(method='right wrist and forearm attached geometry',racket_detector_used=False,
            orientation_measured=False,notes='Racket position follows inferred hand pose; handle and face orientation are illustrative, not measured.'),
        limitations=['Provided camera calibration uses a pinhole model; no distortion parameters or independent calibration uncertainty supplied.',
            'Time offset is estimated from cross-view motion, not hardware synchronization. Exposure/rolling shutter are not corrected.',
            'Ball data are triangulated independently of reference tracking. Missing/rejected positions stay missing.',
            '2D temporal interpolation can be wrong at impacts. The fitted single offset assumes no clock drift over this short rally.',
            'Body landmarks are pretrained estimates; occluded joints may use one-view learned depth anchored to triangulated hips.',
            'Solid figures visualize estimated body motion. Rackets are wrist-attached estimates; spin and racket-face angles are not recovered.',
            'No 3D human or racket ground truth available. Low reprojection error is not proof of body-pose accuracy.'])
    scene=dict(schema_version=2,multiview=True,continuous_avatars=True,title=cfg.get('title','Two-camera rally'),
        units='metres',axes='x table length; y table width; z up; floor at zero',
        duration=float(ta[-1]),fps=ra['fps'],frames=frames,report=report,
        cameras=serial_cameras,source_offsets_seconds=[0,offset],
        table=dict(length=2.74,width=1.525,height=.76,net_height=.1525))
    (out/'scene.json').write_text(json.dumps(scene,separators=(',',':'),allow_nan=False))
    (out/'reconstruction-report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    for path in (ROOT/'web/replay').iterdir():
        if path.is_file():shutil.copy2(path,out/path.name)
    for path in (ROOT/'web/multiview').iterdir():
        if path.is_file():shutil.copy2(path,out/path.name)
    for i,v in enumerate(views):shutil.copy2(v['video'],out/f'source{i+1}.mp4')
    with (out/'ball-3d.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['frame_index','timestamp_seconds','x_m','y_m','z_m','score','status']);w.writeheader()
        for frame in frames:
            b=frame['ball'];pos=b['position'];w.writerow(dict(frame_index=frame['frame_index'],timestamp_seconds=frame['time'],
                x_m=pos[0] if pos else None,y_m=pos[1] if pos else None,z_m=pos[2] if pos else None,score=b['score'],status=b['status']))
    print(json.dumps(dict(output=str(out.resolve()),ball=ball_report,player_pose=pose_report,reconstruction_seconds=report['reconstruction_seconds']),indent=2))
    return scene

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();build(a.config,a.output)

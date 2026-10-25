"""Build an explicitly synthetic 240 FPS fixture for the complete evidence UI.

Known metric coordinates validate the geometry path, not accuracy on phone video.
The source ball follows a known parabola; annotations are ground-truth fixture
inputs, not outputs from a ball/release detector.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import av
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from trophy.serves.legality import analyze_toss, PHASES


def main(output):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    K=np.array([[800.,0,640],[0,800,360],[0,0,1.]])
    def position(t):
        if t<.45:return np.array([-.30,0,.9+(t-.45)*2])
        u=t-.45;return np.array([-.30+.5*u,0,.9+3*u-5*u*u])
    def project(xyz,camera):
        q=K@(np.array(camera['R'])@xyz+camera['t']);return q[:2]/q[2]
    views=[];cameras=[]
    for index,center in enumerate([[-2.,-4,1.5],[2.,-4,1.7]]):
        center=np.array(center);forward=np.array([0,0,1.1])-center;forward/=np.linalg.norm(forward)
        right=np.cross(forward,[0,0,1.]);right/=np.linalg.norm(right)
        down=np.cross(forward,right);R=np.stack([right,down,forward]);t=-R@center
        camera=dict(view_id=f'Fixture camera {index+1}',K=K.tolist(),R=R.tolist(),t=t.tolist(),
                    distortion=[0.]*5,image_size=[1280,720],source_offset_seconds=0.)
        target=out/f'camera{index+1}.mp4'
        with av.open(str(target),'w') as writer:
            stream=writer.add_stream('libx264',rate=240);stream.width=1280;stream.height=720;stream.pix_fmt='yuv420p';stream.options={'crf':'22'}
            for frame in range(288):
                stamp=frame/240;image=np.full((720,1280,3),(21,26,29),np.uint8)
                cv2.putText(image,'SYNTHETIC GEOMETRY VERIFICATION - NOT MATCH FOOTAGE',(38,50),cv2.FONT_HERSHEY_SIMPLEX,.7,(150,220,200),1)
                cv2.putText(image,f'{stamp:.6f} s | known camera matrices and ball coordinates',(38,88),cv2.FONT_HERSHEY_SIMPLEX,.55,(150,170,180),1)
                baseline=np.array([project(np.array([x,0,.76]),camera) for x in np.linspace(-1.37,1.37,20)],np.int32)
                cv2.polylines(image,[baseline],False,(100,120,130),2)
                uv=project(position(stamp),camera);cv2.circle(image,tuple(np.round(uv).astype(int)),7,(65,165,255),-1)
                for packet in stream.encode(av.VideoFrame.from_ndarray(image,format='bgr24')):writer.mux(packet)
            for packet in stream.encode():writer.mux(packet)
        view=dict(id=camera['view_id'],video=str(target),source_size_bytes=target.stat().st_size,
                  source_mtime_ns=target.stat().st_mtime_ns,source_offset_seconds=0.,analyzed_until_seconds=1.19)
        camera['source_identity']={k:view[k] for k in ('video','source_size_bytes','source_mtime_ns')}
        views.append(view);cameras.append(camera)
    report=dict(kind='synthetic_geometry_verification',actual_footage_accuracy=None,
                expected_height_m=.45,expected_angle_degrees=float(np.degrees(np.arctan2(.15,.45))),
                note='Exact source geometry; conservative fixture bounds are assumptions of this test only.')
    raw=json.dumps(report,indent=2).encode();(out/'known-geometry-report.json').write_bytes(raw)
    calibration=dict(format='trophy-toss-calibration-v1',calibration_id='SYNTHETIC-KNOWN-GEOMETRY-ONLY',
        units='metres',fixture_only=True,world_up=[0,0,1],cameras=cameras,validation=dict(status='validated',
        synchronization_verified=True,camera_motion_verified=True,gravity_alignment_verified=True,
        valid_session_time_range_seconds=[0,1.2],position_error_bound_m=.002,maximum_toss_speed_mps=4.,vertical_axis_error_degrees=0.,
        maximum_pair_time_delta_seconds=.0001,
        report=dict(sha256=hashlib.sha256(raw).hexdigest(),method='Exact synthetic geometry; not real-world validation')),
        notes=['Synthetic verification only. Never transfer these validation claims to real video.'])
    request=dict(serve_id='synthetic/serve/1',profile='ittf_ttr_30',observations={},
                 release_bracket_confirmed=True,apex_bracket_confirmed=True)
    for phase,time in zip(PHASES,[106/240,108/240,179/240,180/240,181/240]):
        request['observations'][phase]=[dict(view_id=c['view_id'],source_time_seconds=time,
            uv_norm=(project(position(time),c)/[1280,720]).tolist(),image_size=[1280,720],
            timing_source='decoded_pts',observation_source='synthetic_ground_truth') for c in cameras]
    session=dict(schema_version=1,session_id='synthetic-geometry-verification',title='Synthetic geometry verification · not match footage',
        players={'p0':'Synthetic ball'},views=views,threshold=None,processing_seconds=0.,model={'sha256':'synthetic-known-geometry'},
        synchronization_status='exact_synthetic_frame_alignment',limitations=['This validates code geometry, not real footage accuracy.'],
        events=[dict(serve_id=request['serve_id'],time_seconds=1.,player_id='p0',event_status='review_needed',
                     supporting_views=[v['id'] for v in views],score=None,revision=1,toss_annotations=request)])
    result=analyze_toss(session,request,calibration)
    assert abs(result['metrics']['height_m']-.45)<1e-7
    assert abs(result['metrics']['angle_degrees']-report['expected_angle_degrees'])<1e-7
    assert result['decision']['status']=='two_criteria_satisfied'
    for name,value in [('serves.json',session),('calibration.json',calibration),('annotations.json',request),('verified-evidence.json',result)]:
        (out/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    for file in (ROOT/'web/serves').iterdir():
        if file.is_file():shutil.copy2(file,out/file.name)
    print(json.dumps(dict(output=str(out),height_m=result['metrics']['height_m'],
                         angle_degrees=result['metrics']['angle_degrees'],decision=result['decision']['status']),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default='artifacts/serve-legality/geometry-check')
    main(p.parse_args().output)

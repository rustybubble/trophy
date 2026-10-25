import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from trophy.replay.geometry import calibrate,project,on_plane,reconstruct_players
from trophy.replay.ball import reconstruct_ball


def camera_fixture():
    f=650.;K=np.array([[f,0,640],[0,f,360],[0,0,1.]])
    origin=np.array([.2,-3.5,1.9]);target=np.array([0,0,.76]);forward=target-origin;forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0,0,1.]);right/=np.linalg.norm(right);down=np.cross(forward,right)
    R=np.array([right,down,forward]);return dict(K=K,R=R,t=-R@origin,center=origin)


def test_calibration_and_ray_plane_roundtrip():
    cam=camera_fixture();world=np.array([[-1.37,-.7625,.76],[1.37,-.7625,.76],[1.37,.7625,.76],[-1.37,.7625,.76]])
    cfg=dict(width=1280,height=720,table_corners_px=project(world,cam).tolist(),table_corners_world_m=world.tolist(),focal_length_px=650)
    recovered=calibrate(cfg)
    assert recovered['corner_rmse_px']<1e-5
    for p in world:
        np.testing.assert_allclose(on_plane(project([p],recovered)[0],p[2],recovered),p,atol=1e-5)
    assert recovered['focal_length_assumed']


def test_missing_person_is_not_animated():
    cam=camera_fixture()
    result=reconstruct_players([dict(players=[])],cam)
    assert len(result[0])==2
    assert all(p['joints'] is None and p['status']=='missing' for p in result[0])


def test_occluded_feet_use_explicit_stance_prior():
    cam=camera_fixture();world=np.zeros((33,3));world[:,1]=np.linspace(-.5,.2,33)
    lm=np.tile([400.,310.,.1],(33,1))
    raw=[dict(players=[dict(id=0,world_landmarks=world.tolist(),image_landmarks=lm.tolist(),confidence=.5)])]
    person=reconstruct_players(raw,cam)[0][0]
    assert person['joints'] is not None
    assert person['leg_pose_prior'] and person['anchor_status']=='hip_height_prior_occluded_feet'
    assert abs(person['root'][1])<=1.2


def test_ball_fit_uses_observations_and_marks_gaps():
    cam=camera_fixture();t=np.linspace(0,1,61);events=[dict(frame=0,kind='start'),dict(frame=30,kind='bounce'),dict(frame=60,kind='end')]
    anchors=np.array([[-1.3,0,1.1],[0,0,.78],[1.3,0,1.1]])
    seg=np.minimum((t/.5).astype(int),1);u=(t-seg*.5)/.5
    xyz=anchors[seg]*(1-u[:,None])+anchors[seg+1]*u[:,None];xyz[:,2]+=.5*9.81*(t-seg*.5)*((seg+1)*.5-t)
    pixels=project(xyz,cam)
    rows=[dict(frame_index=i,timestamp_seconds=float(t[i]),detected=i!=15,x=float(p[0]) if i!=15 else None,y=float(p[1]) if i!=15 else None) for i,p in enumerate(pixels)]
    path,report=reconstruct_ball(rows,dict(events=events),cam)
    assert len(path)==61 and report['optimizer_converged']
    assert report['median_reprojection_error_px']<.1
    assert report['measured_3d_accuracy'] is None
    assert path[15]['status']=='inferred_gap' and path[15]['reprojection_error_px'] is None
    assert path[30]['position'][2]==pytest.approx(.78)
    assert all(np.isfinite(p['position']).all() for p in path)


def test_events_must_align_and_cover_clip():
    rows=[dict(timestamp_seconds=i/30,detected=True,x=100,y=100) for i in range(10)]
    with pytest.raises(ValueError,match='cover'):
        reconstruct_ball(rows,dict(events=[dict(frame=1,kind='start'),dict(frame=9,kind='end')]),camera_fixture())

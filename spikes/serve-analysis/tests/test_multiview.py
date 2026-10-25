import csv,json
from pathlib import Path
import numpy as np
import pytest
from trophy.replay.multiview import (load_camera,project,triangulate,fundamental,
    epipolar_distance,sample_detections,synchronize_ball,viewer_coordinates)

ROOT=Path(__file__).resolve().parents[1]


def cameras():
    return [dict(K=np.eye(3),R=np.eye(3),t=np.array([x,0.,0.]),
                 center=np.array([-x,0.,0.]),P=np.c_[np.eye(3),[x,0,0]]) for x in [0.,-1.]]


def test_calibrated_triangulation_and_epipolar_constraint():
    cs=cameras();truth=np.array([.2,.3,3.]);uv=[project(truth,c)[0] for c in cs]
    result=triangulate(uv,cs,max_error=.01)
    assert np.allclose(result['position'],truth,atol=1e-6)
    assert epipolar_distance([uv[0]],[uv[1]],fundamental(*cs))[0]<1e-9


def test_rejects_wrong_correspondences_and_behind_camera():
    cs=cameras();uv=[project([.2,.3,3],c)[0] for c in cs];uv[1][1]+=10
    assert triangulate(uv,cs,max_error=.1) is None
    assert triangulate([project([.2,.3,-3],c)[0] for c in cs],cs) is None


def test_parallel_rays_and_single_view_do_not_fabricate_depth():
    cs=cameras()
    assert triangulate([[0,0]],cs[:1]) is None
    assert triangulate([[0,0],[0,0]],cs) is None


def test_timestamp_sampling_never_bridges_missing_or_extrapolates():
    rows=[dict(timestamp_seconds=t,x=x,y=2*x if x is not None else None,score=.9,detected=d)
          for t,x,d in [(0,0,True),(.02,2,True),(.04,None,False),(.06,6,True)]]
    # Missing detections must have no numeric coordinates.
    rows[2]['y']=None
    sampled=sample_detections(rows,[-.01,0,.01,.03,.05,.08])
    assert sampled[0] is None and sampled[-1] is None
    assert sampled[1]['source_frames']==[0] and not sampled[1]['interpolated']
    assert sampled[2]['x']==1 and sampled[2]['source_frames']==[0,1]
    assert sampled[3] is None and sampled[4] is None


def test_coordinate_conversion_preserves_metric_distances_and_table_height():
    p=np.array([[0,0,0],[.7625,1.37,-.76]])
    q=viewer_coordinates(p)
    assert np.allclose(q[0],[0,0,.76]) and q[1,2]==0
    assert np.linalg.norm(q[1]-q[0])==pytest.approx(np.linalg.norm(p[1]-p[0]))


def test_sync_recovers_offset_for_different_frame_rates():
    # Synthetic geometry exercises clock estimation, not evidence of real tracking.
    cs=cameras();offset=.037
    def make(fps,delay):
        rows=[]
        for t in np.arange(0,2,1/fps):
            u=t-delay;point=[.4*np.sin(u*5),.4*np.sin(u*7)+.2*u,3+.2*np.cos(u*4)]
            uv=project(point,cs[1 if delay else 0])[0]*1
            rows.append(dict(timestamp_seconds=float(t),x=float(uv[0]),y=float(uv[1]),score=.95,detected=True))
        return rows
    found,_=synchronize_ball(make(50,0),make(60,offset),cs)
    assert found==pytest.approx(offset,abs=.002)


def test_sync_boundary_is_reported():
    cs=cameras()
    def rows(delay,cam):
        return [dict(timestamp_seconds=float(t),x=float(project([0,t-delay,3],cam)[0,0]),
                     y=float(project([0,t-delay,3],cam)[0,1]),detected=True,score=.99) for t in np.arange(0,2,.02)]
    with pytest.raises(ValueError,match='search boundary'):
        synchronize_ball(rows(0,cs[0]),rows(.1,cs[1]),cs,search_radius=.02)


def test_real_export_consistency_and_reference_separation():
    path=ROOT/'artifacts/multiview/demo/scene.json'
    if not path.exists():pytest.skip('Run the real two-camera demo first')
    scene=json.loads(path.read_text());rows=list(csv.DictReader(open(path.with_name('ball-3d.csv'))))
    assert len(rows)==len(scene['frames'])==scene['report']['frame_count']
    assert not scene['report']['reference_3d_used_for_reconstruction']
    assert all('reference' not in v for source in scene['report']['source_hashes'] for v in source)
    valid=0
    for frame,row in zip(scene['frames'],rows):
        b=frame['ball'];assert row['status']==b['status']
        if b['position'] is None:assert row['x_m']=='' and b['score'] is None
        else:
            valid+=1;assert np.allclose([float(row[k]) for k in ['x_m','y_m','z_m']],b['position'])
    assert valid==scene['report']['ball']['valid_frames']


@pytest.mark.parametrize('filename',['demo/accuracy.json','rally038-accuracy.json'])
def test_real_reference_validation_regression(filename):
    path=ROOT/'artifacts/multiview'/filename
    if not path.exists():pytest.skip('Download/run the real TT3D validation first')
    data=json.loads(path.read_text());held=data['held_out']
    assert held['predicted_frames']>=90
    assert held['median_error_cm']<5 and held['p95_error_cm']<12
    assert held['coverage']>.9
    end=data['clock_alignment']['calibration_reference_end_seconds']
    assert all(f['reference_timestamp_seconds']>end for f in data['frames'] if f['partition']=='held_out')

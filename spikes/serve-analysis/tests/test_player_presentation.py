import copy,json
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from trophy.replay.avatar import load_avatar,deform
from trophy.replay.motion import smooth_player_motion

ROOT=Path(__file__).resolve().parents[1]


def rest_pose():
    # The generator is the source of truth for the procedural bind pose.
    from trophy.replay.avatar import rest_joints
    return rest_joints()


def test_avatar_is_single_closed_surface_with_normalized_skin_weights():
    for lod in ['low','high']:
        mesh=load_avatar(lod);f=mesh['faces']
        edges=np.sort(np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
        edges,count=np.unique(edges,axis=0,return_counts=True)
        graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(mesh['positions']),)*2)
        assert connected_components(graph,directed=False)[0]==1
        assert np.all(count==2),'Surface has an open seam or non-manifold edge'
        assert np.allclose(mesh['skin_weights'].sum(axis=1),1,atol=1e-6)
        assert mesh['skin_indices'].min()>=0 and mesh['skin_indices'].max()<len(mesh['bones'])


def test_bind_pose_deformation_has_no_gaps_or_distortion():
    asset=load_avatar('high');v,n=deform(rest_pose(),asset)
    assert np.max(np.abs(v-asset['positions']))<1e-5
    assert np.isfinite(n).all() and np.allclose(np.linalg.norm(n,axis=1),1,atol=1e-6)


def test_smoothing_preserves_measurements_missing_frames_and_motion_timing():
    q=rest_pose();frames=[];n=101
    # Smooth forward travel plus alternating jitter; a symmetric filter should
    # remove jitter without shifting the recorded root-motion peak in time.
    for i in range(n):
        joints=q.copy();joints[:,0]+=np.sin(i*.05)+.01*(-1)**i
        frames.append(dict(time=i/50,ball={'position':[1,2,3]},players=[
            dict(id=0,joints=joints.tolist()),dict(id=1,joints=None)]))
    frames[50]['players'][0]['joints']=None
    original=copy.deepcopy(frames);report=smooth_player_motion(frames,50)
    assert report['second_difference_rms_reduction_fraction']>.5
    for before,after in zip(original,frames):
        assert before['ball']==after['ball']
        assert before['players'][0]['joints']==after['players'][0]['joints']
        assert 'render_joints' not in after['players'][1]
    assert 'render_joints' not in frames[50]['players'][0]
    raw=np.array([f['players'][0]['joints'][23][0] for f in original[:49]])
    filtered=np.array([f['players'][0]['render_joints'][23][0] for f in frames[:49]])
    assert abs(raw.argmax()-filtered.argmax())<=1


def test_real_display_motion_has_fixed_limb_lengths_and_preserves_ball():
    path=ROOT/'artifacts/multiview/demo/scene.json'
    if not path.exists():pytest.skip('Build the real multi-view replay first')
    scene=json.loads(path.read_text())
    frames=copy.deepcopy(scene['frames']);balls=[f['ball'] for f in frames]
    report=smooth_player_motion(frames,scene['fps'])
    assert [f['ball'] for f in frames]==balls
    assert report['second_difference_rms_reduction_fraction']>.3
    for pid in [0,1]:
        q=np.array([f['players'][pid]['render_joints'] for f in frames if f['players'][pid].get('render_joints')])
        for a,b in [(11,13),(13,15),(12,14),(14,16),(23,25),(25,27),(24,26),(26,28)]:
            assert np.std(np.linalg.norm(q[:,b]-q[:,a],axis=1))<1e-8

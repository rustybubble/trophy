"""Independent geometric fixtures, boundary cases, and untrusted evidence inputs."""
from copy import deepcopy
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest

from trophy.serves.legality import PHASES, analyze_toss, calibration_from_reconstruction, decide_toss, rulebook, toss_metrics


def fixture():
    """Synthetic cameras/true coordinates, not an accuracy claim on real footage."""
    session=dict(events=[dict(serve_id='s/serve/1',time_seconds=10.)],views=[
        dict(id=name,video=f'/fixture/{name}.mp4',source_size_bytes=123,source_mtime_ns=456,
             source_offset_seconds=offset,analyzed_until_seconds=12.) for name,offset in [('a',0.),('b',.04)]])
    K=np.array([[800.,0,640],[0,800,360],[0,0,1.]])
    cameras=[]
    for v,tx in zip(session['views'],[0.,-1.]):
        cameras.append(dict(view_id=v['id'],K=K.tolist(),R=np.eye(3).tolist(),t=[tx,0.,0.],
            image_size=[1280,720],distortion=[0.]*5,source_offset_seconds=v['source_offset_seconds'],
            source_identity={k:v[k] for k in ('video','source_size_bytes','source_mtime_ns')}))
    calibration=dict(format='trophy-toss-calibration-v1',calibration_id='synthetic-known-geometry',units='metres',
        world_up=[0,1,0],cameras=cameras,validation=dict(status='validated',synchronization_verified=True,
            camera_motion_verified=True,gravity_alignment_verified=True,valid_session_time_range_seconds=[0,12],
            position_error_bound_m=.001,maximum_toss_speed_mps=4.,maximum_pair_time_delta_seconds=.001,vertical_axis_error_degrees=0.,
            report=dict(sha256='f'*64,method='Synthetic known 3D coordinates and bounded perturbations')))
    points=[[.19,.07,3],[.2,.1,3],[.29,.548,3],[.3,.55,3],[.31,.548,3]]
    request=dict(serve_id='s/serve/1',profile='ittf_ttr_30',observations={},
                 release_bracket_confirmed=True,apex_bracket_confirmed=True)
    for phase,xyz,time in zip(PHASES,points,[9.45,9.46,9.60,9.61,9.62]):
        observations=[]
        for v,c in zip(session['views'],cameras):
            p=K@(np.asarray(xyz)+c['t']);uv=p[:2]/p[2]/[1280,720]
            observations.append(dict(view_id=v['id'],source_time_seconds=time+v['source_offset_seconds'],
                uv_norm=uv.tolist(),image_size=[1280,720],timing_source='browser_presented_frame'))
        request['observations'][phase]=observations
    return session,request,calibration


def test_height_is_vertical_rise_not_path_length_or_table_height():
    m=toss_metrics([3,4,10],[3.3,4.4,10.12])
    assert m['height_m']==pytest.approx(.12)
    assert m['horizontal_displacement_m']==pytest.approx(.5)
    assert decide_toss(m)['checks'][0]['result']=='violation_supported'


def test_out_of_image_plane_motion_counts_toward_3d_angle():
    m=toss_metrics([0,0,0],[0,.3,.3])
    assert m['angle_degrees']==pytest.approx(45.)
    assert decide_toss(m)['checks'][1]['result']=='violation_supported'


def test_conservative_bounds_contain_random_true_endpoints():
    rng=np.random.default_rng(19);r=np.array([.3,.4,.2]);a=np.array([.5,.6,.7])
    m=toss_metrics(r,a,release_error_m=.025,apex_error_m=.03)
    for _ in range(300):
        dr=rng.normal(size=3);dr*=rng.uniform(0,.025)/np.linalg.norm(dr)
        da=rng.normal(size=3);da*=rng.uniform(0,.03)/np.linalg.norm(da)
        actual=toss_metrics(r+dr,a+da)
        assert m['height_interval_m'][0]<=actual['height_m']<=m['height_interval_m'][1]
        assert m['angle_interval_degrees'][0]<=actual['angle_degrees']<=m['angle_interval_degrees'][1]


def test_uncertain_vertical_axis_expands_height_and_angle_envelopes():
    r=np.array([.1,.2,.3]);a=np.array([.4,.5,.7]);alpha=3.
    envelope=toss_metrics(r,a,up_error_degrees=alpha,release_error_m=.01)
    for phi in np.linspace(0,2*np.pi,41):
        angle=np.radians(alpha);u=[np.sin(angle)*np.cos(phi),np.sin(angle)*np.sin(phi),np.cos(angle)]
        actual=toss_metrics(r,a,up=u)
        assert envelope['height_interval_m'][0]<=actual['height_m']<=envelope['height_interval_m'][1]
        assert envelope['angle_interval_degrees'][0]<=actual['angle_degrees']<=envelope['angle_interval_degrees'][1]


def test_equality_is_inclusive_and_uncertainty_crossing_threshold_abstains():
    m=toss_metrics([0,0,0],[0,0,.16])
    assert decide_toss(m)['checks'][0]['result']=='criterion_satisfied'
    m=toss_metrics([0,0,0],[0,0,.16],release_error_m=.01)
    assert decide_toss(m)['checks'][0]['result']=='borderline'
    m=toss_metrics([0,0,0],[.2*np.tan(np.radians(30)),0,.2])
    m['angle_interval_degrees']=[30.,30.]
    assert decide_toss(m)['checks'][1]['result']=='criterion_satisfied'
    m['angle_interval_degrees']=[29.,31.]
    assert decide_toss(m)['checks'][1]['result']=='borderline'


def test_published_law_profile_does_not_invent_numeric_angle_rule():
    d=decide_toss(toss_metrics([0,0,0],[.3,0,.3]),profile='ittf_law_2_6_2')
    assert d['checks'][1]['threshold'] is None
    assert d['checks'][1]['result']=='referee_judgment_required'
    assert d['serve_legal'] is None and not d['automatic_point_award']


def test_known_3d_geometry_roundtrip_and_proof_provenance():
    s,r,c=fixture();result=analyze_toss(s,r,c)
    assert np.allclose(result['points']['first_free']['position_m'],[.2,.1,3])
    assert result['metrics']['height_m']==pytest.approx(.45)
    assert result['decision']['status']=='two_criteria_satisfied'
    assert result['decision']['serve_legal'] is None
    assert result['points']['apex']['session_times_seconds']==pytest.approx([9.61,9.61])
    assert result['overlays']['a']['release']==pytest.approx(r['observations']['first_free'][0]['uv_norm'])
    assert result['calibration_sha256'] and result['evidence_id']
    assert result['rulebook']['law']['id']=='2.6.2'
    reproduced=analyze_toss(result['source_session'],result['annotations'],result['calibration'])
    assert reproduced['evidence_id']==result['evidence_id']


@pytest.mark.parametrize('height,lateral,failed_check',[(.06,.02,0),(.45,.4,1)])
def test_stereo_evidence_supports_specific_fault_with_rule_reference(height,lateral,failed_check):
    s,r,c=fixture()
    for phase,delta in [('apex_before',-.002),('apex',0),('apex_after',-.002)]:
        xyz=np.array([.2+lateral,.1+height+delta,3.])
        for o,camera in zip(r['observations'][phase],c['cameras']):
            p=np.asarray(camera['K'])@(xyz+camera['t']);o['uv_norm']=(p[:2]/p[2]/[1280,720]).tolist()
    result=analyze_toss(s,r,c)
    assert result['decision']['status']=='violation_supported'
    check=result['decision']['checks'][failed_check]
    assert check['result']=='violation_supported' and check['rule_id']=='2.6.2'
    assert check['source'].startswith('https://') and check['interval']
    assert result['decision']['serve_legal'] is None and not result['decision']['official_ruling']


@pytest.mark.parametrize('field,value',[
    ('status','unvalidated'),('synchronization_verified',False),('camera_motion_verified',False),
    ('gravity_alignment_verified',False),('position_error_bound_m',None),('report',None),
    ('valid_session_time_range_seconds',[0,1]),('vertical_axis_error_degrees',None)])
def test_missing_measurement_validation_prevents_false_certainty(field,value):
    s,r,c=fixture();c['validation'][field]=value
    result=analyze_toss(s,r,c)
    assert result['decision']['status']=='needs_review'
    assert all(x['result']=='insufficient_evidence' for x in result['decision']['checks'])


def test_missing_release_is_unknown_not_zero_toss_or_a_fault():
    s,r,c=fixture();del r['observations']['last_on_hand']
    result=analyze_toss(s,r,c)
    assert result['metrics'] is None
    assert result['decision']['status']=='needs_review'


def test_a_phase_marked_in_only_one_view_is_incomplete_evidence():
    s,r,c=fixture();r['observations']['last_on_hand']=r['observations']['last_on_hand'][:1]
    result=analyze_toss(s,r,c)
    assert result['metrics'] is None and result['decision']['status']=='needs_review'


def test_no_calibration_does_not_turn_pixels_into_centimetres():
    s,r,c=fixture();result=analyze_toss(s,r)
    assert result['metrics'] is None and result['overlays']=={}
    assert result['decision']['status']=='needs_review'


def test_reconstruction_cameras_are_reused_without_inventing_validation():
    s,r,c=fixture();s['session_id']='fixture'
    derived=calibration_from_reconstruction(s,dict(cameras=c['cameras'],source_sizes=[[1280,720]]*2,world_up=c['world_up']))
    assert derived['cameras'][1]['source_identity']==c['cameras'][1]['source_identity']
    assert derived['validation']['status']=='unvalidated'
    result=analyze_toss(s,r,derived)
    assert result['metrics'] and result['decision']['status']=='needs_review'


def test_manually_added_or_time_adjusted_serves_can_have_reproducible_evidence():
    s,r,c=fixture();s['session_id']='fixture'
    r.update(serve_id='fixture/manual/abc',contact_time_seconds=10.)
    assert analyze_toss(s,r,c)['decision']['status']=='two_criteria_satisfied'
    r['contact_time_seconds']=20.
    with pytest.raises(ValueError,match='outside this recording'):analyze_toss(s,r,c)


def test_roundoff_does_not_turn_exactly_sixteen_cm_into_a_fault():
    m=toss_metrics([0,0,.25],[0,0,.41])
    assert decide_toss(m)['checks'][0]['result']=='criterion_satisfied'


@pytest.mark.parametrize('change,match',[
    ('identity','different source'),('clock','clock offsets'),('correspondence','reprojection'),
    ('timestamp','40 ms'),('order','time order'),('aspect','aspect ratio')])
def test_rejects_mismatched_sources_frames_and_geometry(change,match):
    s,r,c=fixture()
    if change=='identity':c['cameras'][0]['source_identity']['source_size_bytes']=999
    if change=='clock':c['cameras'][0]['source_offset_seconds']=.1
    if change=='correspondence':r['observations']['apex'][1]['uv_norm'][1]+=.2
    if change=='timestamp':r['observations']['apex'][1]['source_time_seconds']+=.1
    if change=='order':r['observations']['last_on_hand']=deepcopy(r['observations']['first_free'])
    if change=='aspect':r['observations']['apex'][1]['image_size']=[720,1280]
    with pytest.raises(ValueError,match=match):analyze_toss(s,r,c)


def test_actual_pair_timing_must_fit_the_validated_envelope():
    s,r,c=fixture();r['observations']['apex'][1]['source_time_seconds']+=.01
    result=analyze_toss(s,r,c)
    assert result['metrics'] and result['decision']['status']=='needs_review'
    assert any('timing envelope' in x for x in result['decision']['blockers'])


def test_release_lift_is_not_silently_counted_as_toss_height():
    s,r,c=fixture();r['release_bracket_confirmed']=False
    result=analyze_toss(s,r,c)
    assert result['decision']['checks'][0]['result']=='insufficient_evidence'
    assert result['metrics']['release_error_bound_m']>.001


def test_bad_points_nan_and_nonunit_vertical_rejected():
    with pytest.raises(ValueError):toss_metrics([0,0,0],[0,np.nan,1])
    with pytest.raises(ValueError):toss_metrics([0,0,0],[0,0,1],up=[0,0,2])
    with pytest.raises(ValueError):toss_metrics([0,0,0],[0,0,1],release_error_m=-1)


@pytest.mark.parametrize('prefix',['','/review'])
def test_local_api_reproduces_proof_and_rejects_cross_origin(tmp_path,prefix):
    spec=importlib.util.spec_from_file_location('toss_review_server',Path(__file__).resolve().parents[1]/'scripts/serve_serve_review.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    s,r,c=fixture();(tmp_path/'serves.json').write_text(json.dumps(s))
    server=ThreadingHTTPServer(('127.0.0.1',0),module.handler_for(tmp_path,c,route_prefix=prefix))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}{prefix}'
    try:
        with urllib.request.urlopen(url+'/api/toss-rules') as response:
            assert json.load(response)['rulebook']==rulebook()
        body=json.dumps(r).encode();headers={'Content-Type':'application/json'}
        with urllib.request.urlopen(urllib.request.Request(url+'/api/toss-measure',body,headers)) as response:
            assert json.load(response)['evidence_id']==analyze_toss(s,r,c)['evidence_id']
        headers['Origin']='https://unrelated.example'
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(url+'/api/toss-measure',body,headers))
        assert error.value.code==403
    finally:server.shutdown();server.server_close();thread.join()

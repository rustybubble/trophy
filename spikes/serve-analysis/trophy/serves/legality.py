"""Evidence-based toss checks. No image-space angle is treated as a 3D angle.

The trusted inputs are source-frame observations plus a separate calibration
validation record. An estimated camera fit can produce an illustration, never a
supported ruling. Bounds are conservative spatial envelopes, not confidence scores.
"""
from copy import deepcopy
import hashlib
import json
import math

import cv2
import numpy as np


STATUTES = 'https://db.ittf.com/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf#page=41'
TTR = 'https://www.ittf.com/2024/12/08/table-tennis-review-system-returns-with-a-successful-trial-at-ittf-mixed-team-world-cup-2024/'
PAPER = 'https://doi.org/10.3390/electronics14010027'
PHASES = ('last_on_hand', 'first_free', 'apex_before', 'apex', 'apex_after')


def calibration_from_reconstruction(session, geometry):
    """Reuse measured camera parameters without promoting a replay fit to proof."""
    views=session['views'];cameras=geometry['cameras'];sizes=geometry['source_sizes']
    if len(views)!=2 or len(cameras)!=2 or len(sizes)!=2:
        raise ValueError('Toss calibration requires two matched reconstruction cameras')
    start=max(0.,*[-v.get('source_offset_seconds',0.) for v in views])
    end=min(v['analyzed_until_seconds']-v.get('source_offset_seconds',0.) for v in views)
    result=dict(format='trophy-toss-calibration-v1',calibration_id=f"{session['session_id']}/replay-geometry",
        units='metres',world_up=geometry.get('world_up',[0,0,1]),cameras=[],validation=dict(status='unvalidated',
        synchronization_verified=False,camera_motion_verified=False,gravity_alignment_verified=False,
        valid_session_time_range_seconds=[start,end],position_error_bound_m=None,maximum_toss_speed_mps=None,
        vertical_axis_error_degrees=None,maximum_pair_time_delta_seconds=None,report=None),
        notes=['Camera matrices are reused from the same two-camera reconstruction and source clips.',
               'The table-corner fit and visual sync estimate have no independently validated toss error bound.',
               'Replay geometry supports provisional overlays, not supported fault calls.'])
    for view,camera,size in zip(views,cameras,sizes):
        result['cameras'].append(dict(view_id=view['id'],K=camera['K'],R=camera['R'],t=camera['t'],
            image_size=size,distortion=camera.get('distortion',[0.]*5),
            source_offset_seconds=view.get('source_offset_seconds',0.),
            source_identity={k:view[k] for k in ('video','source_size_bytes','source_mtime_ns')}))
    return result


def rulebook():
    return dict(version='ittf-2026-law+ttr-2024-v1',
        law=dict(id='2.6.2', title='ITTF Statutes 2026, Law 2.6.2', url=STATUTES,
                 height_minimum_m=.16, height_requirement='Rise of at least 16 cm after leaving the free hand.',
                 angle_requirement='Project the ball near vertically upwards; the published law has no numeric angle.'),
        ttr=dict(title='ITTF TTR review criterion', url=TTR, angle_maximum_degrees=30.,
                 scope='Technology-review criterion; not a universal numeric replacement for near vertically.'),
        method=dict(angle='3D release-to-apex displacement relative to calibrated gravity; not launch velocity.',
                    reference=PAPER, official_ttr_algorithm_verified=False),
        profiles=['ittf_ttr_30', 'ittf_law_2_6_2'],
        unchecked=['spin', 'open stationary palm', 'visibility', 'free-arm removal',
                   'behind end line', 'above table', 'strike while falling', 'bounce sequence'])


def finite(value, name, minimum=None):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be numeric')
    x = float(value)
    if not math.isfinite(x) or (minimum is not None and x < minimum):
        raise ValueError(f'Invalid {name}')
    return x


def toss_metrics(release, apex, *, up=(0, 0, 1), release_error_m=0., apex_error_m=0., up_error_degrees=0.):
    """Propagate bounded endpoint Euclidean errors into conservative intervals.

    This is a geometric envelope, conditional on the supplied error bounds being
    valid. It does not estimate those bounds from a small reprojection residual.
    """
    r, a, u = (np.asarray(x, float) for x in (release, apex, up))
    if any(x.shape != (3,) or not np.isfinite(x).all() for x in (r, a, u)):
        raise ValueError('Expected finite three-dimensional points and vertical')
    if abs(np.linalg.norm(u)-1) > 1e-5:
        raise ValueError('World up must be a unit vector')
    error = finite(release_error_m, 'release error', 0) + finite(apex_error_m, 'apex error', 0)
    axis_error=finite(up_error_degrees,'vertical-axis angular error',0)
    if axis_error>90:raise ValueError('Vertical-axis uncertainty must not exceed 90 degrees')
    delta = a-r
    height = float(delta@u)
    lateral = float(np.linalg.norm(delta-height*u))
    theta = math.degrees(math.atan2(lateral, height))
    hlo, hhi = height-error, height+error
    # atan2 is monotonic here only for a strictly positive rise envelope.
    angle_bounds = [math.degrees(math.atan2(max(0., lateral-error), hhi)),
                    math.degrees(math.atan2(lateral+error, hlo))] if hlo > 0 else [0., 180.]
    angle_bounds=[max(0.,angle_bounds[0]-axis_error),min(180.,angle_bounds[1]+axis_error)]
    vertical_error=float(np.linalg.norm(delta))*2*math.sin(math.radians(axis_error)/2)
    return dict(height_m=height, height_interval_m=[hlo-vertical_error, hhi+vertical_error], horizontal_displacement_m=lateral,
                angle_degrees=theta, angle_interval_degrees=angle_bounds,vertical_axis_error_degrees=axis_error,
                endpoint_error_sum_m=error, uncertainty_type='conditional_conservative_spatial_envelope')


def decide_toss(metrics, blockers=(), profile='ittf_ttr_30'):
    if profile not in rulebook()['profiles']:
        raise ValueError('Unknown rules profile')
    blockers = list(dict.fromkeys(blockers))
    height = dict(rule_id='2.6.2', criterion='rise_after_release', threshold=.16, unit='m',
                  source=STATUTES, result='insufficient_evidence')
    angle = dict(rule_id='2.6.2', criterion='near_vertical', threshold=30. if profile=='ittf_ttr_30' else None,
                 unit='degrees_from_vertical', source=TTR if profile=='ittf_ttr_30' else STATUTES,
                 result='insufficient_evidence', method='release_to_apex_3d_chord',
                 interpretation='Research chord method against published TTR threshold; not an official TTR adjudication')
    if metrics:
        height.update(estimate=metrics['height_m'], interval=metrics.get('height_interval_m'))
        angle.update(estimate=metrics['angle_degrees'], interval=metrics.get('angle_interval_degrees'))
    if metrics and not blockers:
        low, high = height['interval']
        height['result'] = 'violation_supported' if high < .16-1e-9 else ('criterion_satisfied' if low >= .16-1e-9 else 'borderline')
        if profile == 'ittf_ttr_30':
            low, high = angle['interval']
            angle['result'] = 'violation_supported' if low > 30+1e-8 else ('criterion_satisfied' if high <= 30+1e-8 else 'borderline')
        else:
            angle['result'] = 'referee_judgment_required'
    height['explanation']={
        'violation_supported':'Even the upper measurement bound is below the required 16 cm rise.',
        'criterion_satisfied':'Even the lower measurement bound reaches the required 16 cm rise.',
        'borderline':'The measurement envelope crosses 16 cm; it cannot support either conclusion.',
        'insufficient_evidence':'Required source observations or calibration validation are missing.'}[height['result']]
    angle['explanation']={
        'violation_supported':'Even the lower angle bound exceeds the 30° TTR criterion under the documented chord method.',
        'criterion_satisfied':'Even the upper angle bound is within the 30° TTR criterion under the documented chord method.',
        'borderline':'The angle envelope crosses 30°; it cannot support either conclusion.',
        'insufficient_evidence':'Required source observations or calibration validation are missing.',
        'referee_judgment_required':'The published law specifies near vertical without a numeric angle; a referee must interpret this measurement.'}[angle['result']]
    checks = [height, angle]
    status = ('violation_supported' if any(c['result']=='violation_supported' for c in checks)
              else 'two_criteria_satisfied' if all(c['result']=='criterion_satisfied' for c in checks)
              else 'needs_review')
    return dict(status=status, scope='toss_height_and_direction_only', profile=profile, checks=checks,
                blockers=blockers, serve_legal=None, official_ruling=False, automatic_point_award=False,
                explanation='A satisfied toss check does not establish that the whole service is legal.')


def _camera(raw):
    K, R, t = (np.asarray(raw[k], float) for k in ('K', 'R', 't'))
    if K.shape!=(3,3) or R.shape!=(3,3) or t.shape!=(3,) or not all(np.isfinite(x).all() for x in (K,R,t)):
        raise ValueError('Invalid camera matrices')
    if not np.allclose(R@R.T, np.eye(3), atol=1e-4) or np.linalg.det(R)<.99 or K[0,0]<=0 or K[1,1]<=0:
        raise ValueError('Invalid calibrated camera orientation/intrinsics')
    size = np.asarray(raw['image_size'], float)
    if size.shape!=(2,) or not np.isfinite(size).all() or np.any(size<16):
        raise ValueError('Invalid calibration image size')
    distortion = np.asarray(raw.get('distortion', [0]*5), float)
    if distortion.ndim!=1 or len(distortion) not in (4,5,8,12,14) or not np.isfinite(distortion).all():
        raise ValueError('Invalid distortion coefficients')
    return dict(K=K, R=R, t=t, P=K@np.c_[R,t], center=-R.T@t, size=size, distortion=distortion)


def _pair(observations, views, cameras):
    if not isinstance(observations, list) or len(observations)!=2:
        raise ValueError('Each phase needs one ball observation in each camera')
    if {o['view_id'] for o in observations} != {v['id'] for v in views}:
        raise ValueError('Observation cameras must match this recording')
    ordered = [next(o for o in observations if o['view_id']==v['id']) for v in views]
    pixels, times = [], []
    for o, v, c in zip(ordered, views, cameras):
        uv = np.asarray(o['uv_norm'], float)
        if uv.shape!=(2,) or not np.isfinite(uv).all() or np.any(uv<0) or np.any(uv>1):
            raise ValueError('Ball center must be inside the source image')
        size=np.asarray(o['image_size'], float)
        if size.shape!=(2,) or not np.isfinite(size).all() or np.any(size<16) or abs(size[0]/size[1]-c['size'][0]/c['size'][1])>.001:
            raise ValueError('Source aspect ratio differs from its calibration')
        stamp=finite(o['source_time_seconds'], 'source frame time', 0)
        if stamp > v['analyzed_until_seconds']+.05:
            raise ValueError('Observation is outside the analyzed recording')
        times.append(stamp-v.get('source_offset_seconds',0.))
        pixels.append(cv2.undistortPoints((uv*c['size']).reshape(1,1,2), c['K'], c['distortion'], P=c['K']).reshape(2))
    if abs(times[0]-times[1])>.04:
        raise ValueError('Marked frames differ by more than 40 ms on the session clock')
    h=cv2.triangulatePoints(cameras[0]['P'],cameras[1]['P'],pixels[0],pixels[1]).ravel()
    if not np.isfinite(h).all() or abs(h[3])<1e-10:
        raise ValueError('Ball rays cannot be triangulated')
    xyz=h[:3]/h[3];errors=[];rays=[]
    for uv,c in zip(pixels,cameras):
        q=c['R']@xyz+c['t']
        if q[2]<=0:raise ValueError('Triangulation lies behind a camera')
        p=c['K']@q;errors.append(float(np.linalg.norm(p[:2]/p[2]-uv)))
        ray=xyz-c['center'];rays.append(ray/np.linalg.norm(ray))
    angle=math.degrees(math.acos(np.clip(abs(rays[0]@rays[1]),-1,1)))
    if max(errors)>6 or angle<3:
        raise ValueError('Ball correspondence fails reprojection/parallax checks')
    return dict(position_m=xyz.tolist(), time_seconds=float(np.mean(times)),
                session_times_seconds=times, pair_time_delta_seconds=abs(times[0]-times[1]),
                reprojection_errors_px=errors, ray_angle_degrees=angle,
                observations=deepcopy(ordered))


def _project(point, camera):
    uv,_=cv2.projectPoints(np.asarray(point,float).reshape(1,3), cv2.Rodrigues(camera['R'])[0],
                           camera['t'],camera['K'],camera['distortion'])
    return (uv.reshape(2)/camera['size']).tolist()


def analyze_toss(session, request, calibration=None):
    """Consume reviewable frame markers; return a rule-linked proof bundle.

    Camera/uncertainty settings are server-owned, never accepted from the POST.
    No phase is inferred from the contact spotter or from a missing ball detection.
    """
    event=next((e for e in session['events'] if e['serve_id']==request.get('serve_id')),None)
    manual_id=f"{session.get('session_id','session')}/manual/"
    if event is None:
        if not str(request.get('serve_id','')).startswith(manual_id) or 'contact_time_seconds' not in request:
            raise ValueError('Select a detector event or an explicitly added manual serve')
        event=dict(serve_id=request['serve_id'],time_seconds=request['contact_time_seconds'],review_source='human_added')
    if 'contact_time_seconds' in request:
        event=dict(event,time_seconds=finite(request['contact_time_seconds'],'reviewed contact time',0))
    duration=min(v['analyzed_until_seconds']-v.get('source_offset_seconds',0.) for v in session['views'])
    if not 0<=event['time_seconds']<=duration:raise ValueError('Contact time is outside this recording')
    profile=request.get('profile','ittf_ttr_30')
    if profile not in rulebook()['profiles']:raise ValueError('Unknown rules profile')
    observations=request.get('observations',{})
    if not isinstance(observations,dict) or any(k not in PHASES for k in observations):
        raise ValueError('Unknown toss phase')
    blockers=[];points={};metrics=None;overlays={}
    if len(session['views'])!=2:blockers.append('Two camera views are required for this metric method.')
    if not calibration:blockers.append('No metric camera calibration is configured.')
    for values in observations.values():
        if not isinstance(values,list) or len(values)>2 or len({o['view_id'] for o in values})!=len(values):
            raise ValueError('At most one observation per camera and phase is allowed')
        if any(o['view_id'] not in {v['id'] for v in session['views']} for o in values):
            raise ValueError('Observation cameras must match this recording')
    missing=[p for p in PHASES if len(observations.get(p,[]))!=2]
    if missing:blockers.append('Mark both camera frames for: '+', '.join(missing)+'.')
    if request.get('release_bracket_confirmed') is not True:
        blockers.append('Reviewer must verify the last-on-hand / first-free release bracket.')
    if request.get('apex_bracket_confirmed') is not True:
        blockers.append('Reviewer must inspect the full toss and verify a bracket around its highest point.')
    if calibration and len(session['views'])==2:
        if calibration.get('format')!='trophy-toss-calibration-v1' or calibration.get('units')!='metres':
            raise ValueError('Unsupported toss calibration format/units')
        if [c['view_id'] for c in calibration['cameras']]!=[v['id'] for v in session['views']]:
            raise ValueError('Calibration camera order must match session views')
        for c,v in zip(calibration['cameras'],session['views']):
            expected=c.get('source_identity',{})
            actual={k:v.get(k) for k in ('video','source_size_bytes','source_mtime_ns')}
            if expected!=actual:raise ValueError('Calibration belongs to different source video bytes')
            if c.get('source_offset_seconds')!=v.get('source_offset_seconds',0.):
                raise ValueError('Camera clock offsets differ from the calibration record')
        cameras=[_camera(c) for c in calibration['cameras']]
        up=np.asarray(calibration['world_up'],float)
        if up.shape!=(3,) or not np.isfinite(up).all() or abs(np.linalg.norm(up)-1)>1e-5:
            raise ValueError('Calibrated vertical must be a unit vector')
        for phase in PHASES:
            if len(observations.get(phase,[]))==2:points[phase]=_pair(observations[phase],session['views'],cameras)
        validation=calibration.get('validation',{})
        if validation.get('status')!='validated':blockers.append('Camera geometry and 3D error bounds have not been validated for toss decisions.')
        for key,label in [('synchronization_verified','Visual synchronization'),('camera_motion_verified','Camera stability'),('gravity_alignment_verified','Gravity alignment')]:
            if validation.get(key) is not True:blockers.append(label+' has not been verified for this interval.')
        scope=validation.get('valid_session_time_range_seconds')
        if not scope or len(scope)!=2 or any(not scope[0]<=t<=scope[1] for p in points.values() for t in p['session_times_seconds']):
            blockers.append('Marks fall outside the validated calibration interval.')
        bound=validation.get('position_error_bound_m');speed=validation.get('maximum_toss_speed_mps')
        axis_error=validation.get('vertical_axis_error_degrees')
        if axis_error is None:blockers.append('A validated gravity-axis angular error bound is required.')
        else:axis_error=finite(axis_error,'vertical-axis angular error',0)
        report=validation.get('report')
        if bound is None or speed is None or not isinstance(report,dict) or not report.get('sha256') or not report.get('method'):
            blockers.append('A source-linked 3D error-bound / timing validation report is required.')
            bound=speed=None
        else:
            bound=finite(bound,'position error bound',0);speed=finite(speed,'maximum toss speed',0)
            pair_limit=finite(validation.get('maximum_pair_time_delta_seconds',0),'pair time limit',0)
            if any(p['pair_time_delta_seconds']>pair_limit+1e-6 for p in points.values()):
                blockers.append('Paired source frames exceed the validated timing envelope.')
        if all(p in points for p in PHASES):
            ts=[points[p]['time_seconds'] for p in PHASES]
            if not all(a<b for a,b in zip(ts,ts[1:])):
                raise ValueError('Expected last-on-hand, first-free, pre-apex, apex, post-apex in time order')
            if ts[-1]>event['time_seconds']+.35 or ts[0]<event['time_seconds']-3.5:
                raise ValueError('Toss marks must precede and belong to the selected serve contact')
            if ts[1]-ts[0]>.05 or ts[4]-ts[2]>.1:
                blockers.append('Release/apex brackets are too wide; inspect adjacent source frames.')
            r=np.array(points['first_free']['position_m']);a=np.array(points['apex']['position_m'])
            if float((a-r)@up)<=0:raise ValueError('The marked apex must be above the release')
            if any(float((np.array(points[p]['position_m'])-a)@up)>.01 for p in ('apex_before','apex_after')):
                blockers.append('A neighboring observation is above the marked apex.')
            # Before-release hand motion does not count toward the 16 cm rise.
            # First-free is a nominal anchor; the unknown release within its
            # bracket expands the envelope by the validated maximum speed.
            if bound is not None:
                re=bound+speed*(ts[1]-ts[0])
                ae=bound+speed*max(ts[3]-ts[2],ts[4]-ts[3])
                metrics=toss_metrics(r,a,up=up,release_error_m=re,apex_error_m=ae,up_error_degrees=axis_error or 0.)
                metrics.update(release_error_bound_m=re,apex_error_bound_m=ae)
            else:
                metrics=toss_metrics(r,a,up=up)
                metrics.update(height_interval_m=None,angle_interval_degrees=None,
                               uncertainty_type='unvalidated_estimate_no_error_bound')
            vertical=r+up*float((a-r)@up)
            reference=r+up*.16
            for view,camera in zip(session['views'],cameras):
                overlays[view['id']]=dict(release=_project(r,camera),apex=_project(a,camera),
                    vertical_at_apex=_project(vertical,camera),height_reference_16cm=_project(reference,camera),
                    endpoints_time_seconds=[points['first_free']['session_times_seconds'][len(overlays)],
                                            points['apex']['session_times_seconds'][len(overlays)]],
                    label='3D projection; angle value is not the apparent screen angle')
    decision=decide_toss(metrics,blockers,profile)
    fingerprint=hashlib.sha256(json.dumps(dict(request=request,calibration=calibration,rule_version=rulebook()['version']),sort_keys=True,allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1,evidence_id=f'toss/{fingerprint[:20]}',serve_id=event['serve_id'],
                source_session=dict(session_id=session.get('session_id','session'),views=deepcopy(session['views']),events=[deepcopy(event)]),
                rulebook=rulebook(),decision=decision,metrics=metrics,points=points,overlays=overlays,
                annotations=deepcopy(request),calibration_id=calibration.get('calibration_id') if calibration else None,
                calibration=deepcopy(calibration),
                calibration_sha256=hashlib.sha256(json.dumps(calibration,sort_keys=True).encode()).hexdigest() if calibration else None,
                evidence_status='review_assisted',angle_method='release_to_apex_3d_chord',
                limitations=['Release/apex markers are human observations, not model predictions.',
                             'The chord method is a documented research method; official TTR algorithm equivalence is unverified.',
                             'Small reprojection residual does not validate metric scale or release timing.'])

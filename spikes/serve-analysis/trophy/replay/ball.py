"""Approximate monocular flight fitting, never presented as measured 3D.

Fits continuous event positions to actual BlurBall image observations. Each flight
uses constant-gravity ballistic interpolation between event endpoints. Bounce
height is constrained to table height + ball radius. Drag/spin are not recovered.
"""
import numpy as np
from scipy.optimize import least_squares
from .geometry import on_plane, project


def reconstruct_ball(detections, config, camera):
    times = np.array([r['timestamp_seconds'] for r in detections])
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError('At least two monotonic frame timestamps required')
    events = config['events']
    indices = np.array([e['frame'] for e in events], int)
    if indices[0] != 0 or indices[-1] != len(times)-1 or np.any(np.diff(indices) <= 0):
        raise ValueError('Events must cover the entire clip in increasing frame order')
    event_times = times[indices]
    valid = np.array([r['detected'] for r in detections])
    if valid.sum() < 6:
        raise ValueError('Too few real ball observations for reconstruction')
    observation = np.array([[r['x'] or 0, r['y'] or 0] for r in detections], float)
    vi = np.flatnonzero(valid)
    event_pixels = np.column_stack([np.interp(indices, vi, observation[vi, k]) for k in range(2)])
    initial = []
    fixed = {}
    for i, e in enumerate(events):
        z = .78 if e['kind'] == 'bounce' else 1.0
        point = on_plane(event_pixels[i], z, camera)
        if point is None:
            point = np.array([0, 0, z])
        point[:2] = np.clip(point[:2], [-3.3, -1.3], [3.3, 1.3])
        if e['kind'] == 'bounce':
            fixed[i] = .78
        initial.append(point)
    initial = np.array(initial)
    free = [(i, k) for i in range(len(events)) for k in range(3) if not (i in fixed and k == 2)]
    x0 = np.array([initial[i,k] for i,k in free])
    lo = np.array([[-4, -2, .78][k] for i,k in free])
    hi = np.array([[4, 2, 2.8][k] for i,k in free])
    segments = np.clip(np.searchsorted(event_times, times, side='right')-1, 0, len(events)-2)
    dt = event_times[segments+1]-event_times[segments]
    u = (times-event_times[segments])/dt
    gravity_arch = .5*9.81*(times-event_times[segments])*(event_times[segments+1]-times)
    def unpack(x):
        points=initial.copy()
        for v,(i,k) in zip(x,free):points[i,k]=v
        return points
    def path(x):
        p=unpack(x)
        xyz=p[segments]*(1-u[:,None])+p[segments+1]*u[:,None]
        xyz[:,2]+=gravity_arch
        return xyz
    def residual(x):
        reprojection=(project(path(x)[valid],camera)-observation[valid]).ravel()/3
        points=unpack(x)
        # Weak depth priors regularize single-camera ambiguity. They are not data.
        prior=(points[:,:2]-initial[:,:2]).ravel()/1.5
        bounce_bounds=[]
        for i in fixed:
            bounce_bounds.extend([max(0,abs(points[i,0])-1.37)*15,
                                  max(0,abs(points[i,1])-.7625)*15])
        return np.r_[reprojection,prior,bounce_bounds]
    fit=least_squares(residual,np.clip(x0,lo+1e-5,hi-1e-5),bounds=(lo,hi),loss='soft_l1',f_scale=2,max_nfev=500)
    xyz=path(fit.x)
    error=np.linalg.norm(project(xyz,camera)-observation,axis=1)
    output=[]
    for i,r in enumerate(detections):
        output.append(dict(position=xyz[i].tolist(),status='fitted_from_2d' if valid[i] else 'inferred_gap',
                           observed_2d=bool(valid[i]),reprojection_error_px=float(error[i]) if valid[i] else None))
    event_points=unpack(fit.x)
    summary=dict(method='piecewise constant-gravity fit to pretrained BlurBall image detections',
                 inferred_3d=True, measured_3d_accuracy=None, optimizer_converged=bool(fit.success),
                 median_reprojection_error_px=float(np.median(error[valid])),
                 p95_reprojection_error_px=float(np.percentile(error[valid],95)),
                 max_reprojection_error_px=float(np.max(error[valid])),
                 observed_2d_frames=int(valid.sum()),inferred_gap_frames=int((~valid).sum()),
                 events=[{**e,'time':float(times[e['frame']]),'position':p.tolist(),
                          'status':'approximate_event_anchor'} for e,p in zip(events,event_points)],
                 notes=['All depths are inferred from one view; low reprojection error is not proof of 3D accuracy.',
                        'Event boundaries are explicitly configured from 2D changes, not independently measured contacts.',
                        'Gravity=9.81m/s²; no aerodynamic drag, spin or racket dynamics estimated.',
                        'The original missing detections remain missing in source data; fitted gaps have their own status.'])
    return output,summary

"""Calibrated, timestamp-based multi-view reconstruction. No reference-track input.

Camera convention follows OpenCV: X_camera = R X_world + t. TT3D raw
coordinates are table-centred, X across the width, Y along the length, Z up.
The viewer uses [-Y, X, Z + .76] so the floor is at zero.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import yaml
from scipy.interpolate import interp1d
from scipy.optimize import least_squares, minimize_scalar

BODY_EDGES = [(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),
              (12,24),(23,24),(23,25),(25,27),(24,26),(26,28),
              (27,29),(29,31),(28,30),(30,32)]
CORE = [0,11,12,13,14,15,16,23,24,25,26,27,28,29,30,31,32]


def load_camera(path, width=1920, height=1080):
    d = yaml.safe_load(Path(path).read_text())
    K = np.array([[d['f'],0,width/2],[0,d['f'],height/2],[0,0,1.]],float)
    R = cv2.Rodrigues(np.array(d['rvec'],float))[0]
    t = np.array(d['tvec'],float)
    return dict(K=K,R=R,t=t,P=K@np.c_[R,t],center=-R.T@t)


def project(points, camera):
    p = np.atleast_2d(points)@camera['R'].T + camera['t']
    uv = p@camera['K'].T
    return uv[:,:2]/uv[:,2:3]


def fundamental(a,b):
    R = b['R']@a['R'].T
    t = b['t']-R@a['t']
    tx = np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])
    return np.linalg.inv(b['K']).T@tx@R@np.linalg.inv(a['K'])


def epipolar_distance(uv_a,uv_b,F):
    a=np.c_[np.atleast_2d(uv_a),np.ones(len(np.atleast_2d(uv_a)))]
    b=np.c_[np.atleast_2d(uv_b),np.ones(len(np.atleast_2d(uv_b)))]
    lb=a@F.T;la=b@F
    e=np.abs(np.sum(b*lb,axis=1))
    return e*np.sqrt(1/np.maximum(1e-12,np.sum(lb[:,:2]**2,axis=1))+
                     1/np.maximum(1e-12,np.sum(la[:,:2]**2,axis=1)))


def triangulate(observations,cameras,weights=None,max_error=12.,min_angle_deg=1.):
    """DLT + robust reprojection refinement; reject behind-camera/weak solutions."""
    if len(observations)<2 or len(observations)!=len(cameras):
        return None
    observations=np.asarray(observations,float)
    if observations.shape!=(len(cameras),2) or not np.isfinite(observations).all():
        return None
    weights=np.ones(len(cameras)) if weights is None else np.asarray(weights)
    if weights.shape!=(len(cameras),) or not np.isfinite(weights).all() or np.any(weights<=0):
        raise ValueError('Triangulation weights must be positive and match the cameras')
    A=[]
    for uv,c,w in zip(observations,cameras,weights):
        A.extend([np.sqrt(w)*(uv[0]*c['P'][2]-c['P'][0]),np.sqrt(w)*(uv[1]*c['P'][2]-c['P'][1])])
    _,_,vt=np.linalg.svd(A)
    if abs(vt[-1,3])<1e-12:return None
    initial=vt[-1,:3]/vt[-1,3]
    fit=least_squares(lambda x:np.concatenate([(project(x,c)[0]-uv)*np.sqrt(w)
                     for uv,c,w in zip(observations,cameras,weights)]),initial,loss='huber',f_scale=3,max_nfev=25)
    x=fit.x
    if any((c['R']@x+c['t'])[2]<=0 for c in cameras):return None
    errors=[float(np.linalg.norm(project(x,c)[0]-uv)) for uv,c in zip(observations,cameras)]
    rays=[(x-c['center'])/np.linalg.norm(x-c['center']) for c in cameras]
    angle=max(np.degrees(np.arccos(np.clip(abs(a@b),-1,1))) for a in rays for b in rays)
    if max(errors)>max_error or angle<min_angle_deg:return None
    return dict(position=x,reprojection_errors_px=errors,ray_angle_deg=float(angle))


def pose_array(path):
    d=json.loads(Path(path).read_text());n=len(d['frames'])
    a=np.full((n,2,33,3),np.nan)
    for i,f in enumerate(d['frames']):
        for p in f['players']:a[i,p['id']]=p['image_landmarks']
    return np.array([f['timestamp_seconds'] for f in d['frames']]),a,d['report']


def pose_world_array(path):
    d=json.loads(Path(path).read_text());a=np.full((len(d['frames']),2,33,3),np.nan)
    for i,f in enumerate(d['frames']):
        for p in f['players']:a[i,p['id']]=p['world_landmarks']
    return a


def synchronize_poses(ta,a,tb,b,cameras,search=(-.25,.25)):
    """Estimate t_b = t_a + offset using cross-view epipolar consistency.

    Uses moving wrists/elbows, never reference 3D. A time offset estimate is
    not hardware synchronization; rolling shutter/exposure remain unmodelled.
    """
    F=fundamental(*cameras)
    joints=[13,14,15,16]
    inter=interp1d(tb,b,axis=0,bounds_error=False,fill_value=np.nan)
    def cost(offset):
        bb=inter(ta+offset)
        aa=a[:,:,joints];bb=bb[:,:,joints]
        mask=np.isfinite(aa).all(axis=-1)&np.isfinite(bb).all(axis=-1)&(aa[...,2]>.65)&(bb[...,2]>.65)
        errors=epipolar_distance(aa[mask,:2],bb[mask,:2],F)
        # Trim outlying pose landmarks; the same trimmed objective for all offsets.
        return float(np.mean(np.minimum(errors,25.))) if len(errors)>30 else 1e9
    grid=np.arange(search[0],search[1]+.0001,.002)
    costs=np.array([cost(x) for x in grid]);best=int(costs.argmin())
    fit=minimize_scalar(cost,bounds=(max(search[0],grid[best]-.004),min(search[1],grid[best]+.004)),method='bounded')
    return float(fit.x),dict(method='moving-arm epipolar residual, no 3D reference used',
        offset_b_minus_a_seconds=float(fit.x),zero_offset_cost_px=cost(0),best_cost_px=float(fit.fun),
        search_seconds=list(search),curve=[dict(offset_seconds=float(x),cost_px=float(y)) for x,y in zip(grid,costs)])


def viewer_coordinates(points):
    p=np.asarray(points);return np.stack([-p[...,1],p[...,0],p[...,2]+.76],axis=-1)


def sample_detections(rows, times, max_gap=.045):
    """Linear interpolation between consecutive valid measurements only.

    No extrapolation, and no interpolation across missing detections or long gaps.
    This is needed when cameras have different frame rates, not a ball simulator.
    """
    ts=np.array([r['timestamp_seconds'] for r in rows])
    result=[]
    for t in times:
        k=int(np.searchsorted(ts,t))
        if k<len(ts) and abs(ts[k]-t)<1e-7:
            r=rows[k];result.append(dict(x=r['x'],y=r['y'],score=r['score'],source_frames=[k],interpolated=False) if r['detected'] else None)
        elif k==0 or k==len(ts) or ts[k]-ts[k-1]>max_gap or not rows[k]['detected'] or not rows[k-1]['detected']:
            result.append(None)
        else:
            u=(t-ts[k-1])/(ts[k]-ts[k-1]);a,b=rows[k-1],rows[k]
            result.append(dict(x=(1-u)*a['x']+u*b['x'],y=(1-u)*a['y']+u*b['y'],
                score=min(a['score'],b['score']),source_frames=[k-1,k],interpolated=True))
    return result


def synchronize_ball(a,b,cameras,initial=0,search_radius=.15):
    F=fundamental(*cameras);ta=np.array([r['timestamp_seconds'] for r in a])
    def cost(offset):
        aligned=sample_detections(b,ta+offset);uv_a=[];uv_b=[]
        for x,y in zip(a,aligned):
            if x['detected'] and y and min(x['score'],y['score'])>.7:
                uv_a.append([x['x'],x['y']]);uv_b.append([y['x'],y['y']])
        if len(uv_a)<30:return 1e6
        e=epipolar_distance(uv_a,uv_b,F)
        return float(np.mean(np.minimum(e,15)))
    grid=np.linspace(initial-search_radius,initial+search_radius,161);costs=[cost(x) for x in grid];i=int(np.argmin(costs))
    if i in (0,len(grid)-1):
        raise ValueError('Ball synchronization optimum hits search boundary; increase search_radius or provide a coarse offset')
    fit=minimize_scalar(cost,bounds=(grid[max(0,i-1)],grid[min(len(grid)-1,i+1)]),method='bounded')
    return float(fit.x),dict(method='ball epipolar residual using measured 2D model detections; no reference 3D',
        offset_b_minus_a_seconds=float(fit.x),cost_px=float(fit.fun),zero_offset_cost_px=cost(0),
        pose_initial_offset_seconds=initial,
        curve=[dict(offset_seconds=float(x),cost_px=float(y)) for x,y in zip(grid,costs)])


def reconstruct_ball(a,b,cameras,offset,max_error=8.):
    aligned=sample_detections(b,np.array([r['timestamp_seconds'] for r in a])+offset)
    output=[];errors=[];angles=[]
    for row,other in zip(a,aligned):
        result=None
        if row['detected'] and other:
            result=triangulate([[row['x'],row['y']],[other['x'],other['y']]],cameras,max_error=max_error)
        if result and (not -.1<result['position'][2]<2.5 or np.linalg.norm(result['position'][:2])>5):result=None
        if result:
            errors.extend(result['reprojection_errors_px']);angles.append(result['ray_angle_deg'])
            output.append(dict(position=viewer_coordinates(result['position']).tolist(),
                raw_world_position_m=result['position'].tolist(),observed_2d=True,status='triangulated',
                score=min(row['score'],other['score']),reprojection_errors_px=result['reprojection_errors_px'],
                camera_b_source_frames=other['source_frames'],camera_b_temporal_interpolation=other['interpolated'],
                ray_angle_deg=result['ray_angle_deg']))
        else:output.append(dict(position=None,observed_2d=False,status='missing_or_rejected',score=None))
    # Remove isolated spatial outliers without replacing them with simulated positions.
    for i in range(1,len(output)-1):
        prev,cur,nxt=output[i-1:i+2]
        if all(p['position'] is not None for p in [prev,cur,nxt]):
            pa,pb,pc=[np.array(p['position']) for p in [prev,cur,nxt]]
            if min(np.linalg.norm(pb-pa),np.linalg.norm(pb-pc))>.6 and np.linalg.norm(pc-pa)<.25:
                output[i]=dict(position=None,observed_2d=False,status='temporal_outlier_rejected',score=None)
    return output,dict(method='calibrated two-view triangulation, no physics trajectory or reference positions used',
        median_reprojection_error_px=float(np.median(errors)) if errors else None,
        p95_reprojection_error_px=float(np.percentile(errors,95)) if errors else None,
        median_ray_angle_deg=float(np.median(angles)) if angles else None,
        valid_frames=sum(x['position'] is not None for x in output),total_frames=len(output),
        max_per_view_reprojection_error_px=max_error,missing_positions_fabricated=False)


def reconstruct_poses(ta,a,tb,b,cameras,offset,world_b=None):
    aligned=interp1d(tb,b,axis=0,bounds_error=False,fill_value=np.nan)(ta+offset)
    positions=np.full((*a.shape[:3],3),np.nan);errors=[];valid=0
    for i in range(len(ta)):
        for pid in range(2):
            for j in range(33):
                u,v=a[i,pid,j],aligned[i,pid,j]
                if not np.isfinite([u,v]).all() or min(u[2],v[2])<.3:continue
                result=triangulate([u[:2],v[:2]],cameras,weights=[max(.1,u[2]),max(.1,v[2])],max_error=30)
                if result and -.85<result['position'][2]<1.7 and np.linalg.norm(result['position'][:2])<5:
                    positions[i,pid,j]=result['position'];errors.extend(result['reprojection_errors_px']);valid+=1
    # Joint gaps <= 100ms may be interpolated, explicitly flagged in export.
    observed=np.isfinite(positions).all(axis=-1)
    for pid in range(2):
        for j in range(33):
            good=np.where(observed[:,pid,j])[0]
            for l,r in zip(good[:-1],good[1:]):
                if r>l+1 and ta[r]-ta[l]<=.100001:
                    for k in range(l+1,r):positions[k,pid,j]=positions[l,pid,j]+(positions[r,pid,j]-positions[l,pid,j])*(ta[k]-ta[l])/(ta[r]-ta[l])
    raw=positions.copy()
    mono=None
    if world_b is not None:
        mono=interp1d(tb,world_b,axis=0,bounds_error=False,fill_value=np.nan)(ta+offset)
        mono=(mono-mono[:,:,[23,24]].mean(axis=2)[:,:,None])@cameras[1]['R']
    # Where one view hides a leg, use the other view's learned relative depth
    # anchored to the triangulated hips. Keep that distinction in each frame.
    if mono is not None:
        for i in range(len(ta)):
            for pid in range(2):
                if np.isfinite(raw[i,pid,[23,24]]).all():
                    root=raw[i,pid,[23,24]].mean(axis=0)
                    for j in CORE:
                        if not np.isfinite(raw[i,pid,j]).all() and np.isfinite(mono[i,pid,j]).all():
                            raw[i,pid,j]=mono[i,pid,j]+root
    # Bone lengths learned robustly from the two-view triangulations in this clip.
    lengths={}
    for pid in range(2):
        for u,v in BODY_EDGES:
            q=np.linalg.norm(raw[:,pid,u]-raw[:,pid,v],axis=-1)
            good=q[np.isfinite(q)&(q>.03)&(q<.8)]
            lengths[pid,u,v]=float(np.median(good)) if len(good) else .3
    output=[];optimized_errors=[]
    for i,t in enumerate(ta):
        people=[]
        for pid in range(2):
            init=raw[i,pid].copy()
            core_ok=np.isfinite(init[CORE]).all(axis=-1)
            if core_ok.sum()<len(CORE)-2:
                people.append(dict(id=pid,joints=None,status='missing',confidence=0));continue
            # Unreliable face/hand detail is tied to measured nearby joints, not animated.
            for j in range(33):
                if not np.isfinite(init[j]).all():
                    anchor=0 if j<=10 else (15 if j in [17,19,21] else 16 if j in [18,20,22] else 27 if j in [29,31] else 28)
                    if np.isfinite(init[anchor]).all():init[j]=init[anchor]
            if not np.isfinite(init).all():
                people.append(dict(id=pid,joints=None,status='missing',confidence=0));continue
            # Per-frame constrained fit uses both cameras plus metric bone lengths.
            # Only core joints are optimized; no gait, swing, or neutral stance generated.
            ids=CORE;index={j:k for k,j in enumerate(ids)}
            def residual(flat):
                x=flat.reshape(-1,3);res=[]
                for cam,lm in zip(cameras,[a[i,pid],aligned[i,pid]]):
                    uv=project(x,cam);target=lm[ids,:2];w=np.sqrt(np.clip(lm[ids,2],0,1))
                    ok=np.isfinite(target).all(axis=1)&np.isfinite(w)&(lm[ids,2]>=.3)
                    res.extend(((uv[ok]-target[ok])*w[ok,None]/5).ravel())
                for u,v in BODY_EDGES:
                    res.append((np.linalg.norm(x[index[u]]-x[index[v]])-lengths[pid,u,v])/.035)
                res.extend(((x-init[ids])/.25).ravel())
                # Floor is measured by known tabletop height, not inferred hip height.
                for j in [29,30,31,32]:res.append(min(0,x[index[j],2]+.76)/.02)
                return np.array(res)
            fit=least_squares(residual,init[ids].ravel(),loss='soft_l1',max_nfev=12)
            init[ids]=fit.x.reshape(-1,3)
            for cam,lm in zip(cameras,[a[i,pid],aligned[i,pid]]):
                e=np.linalg.norm(project(init[CORE],cam)-lm[CORE,:2],axis=-1)
                optimized_errors.extend(e[np.isfinite(e)&(lm[CORE,2]>=.3)].tolist())
            joints=viewer_coordinates(init)
            people.append(dict(id=pid,joints=joints.tolist(),root=joints[[23,24]].mean(axis=0).tolist(),
                confidence=float(np.nanmean(a[i,pid,CORE,2])),status='two_view_pose_fit',
                triangulated_joint_mask=observed[i,pid].tolist(),leg_pose_prior=False,
                racket=dict(hand='right',status='wrist_attached_orientation_estimate',orientation_measured=False)))
        output.append(people)
    return output,dict(method='two-view 2D MediaPipe landmarks + calibrated triangulation + robust bone-length fit',
        triangulated_joint_observations=valid,possible_joint_observations=int(np.prod(observed.shape)),
        raw_joint_reprojection_median_px=float(np.median(errors)),
        fitted_joint_reprojection_median_px=float(np.median(optimized_errors)),
        fitted_joint_reprojection_p95_px=float(np.percentile(optimized_errors,95)),
        pose_3d_ground_truth_available=False,
        occluded_joint_policy='camera B pretrained relative-depth estimate anchored to triangulated hips; bone-constrained fit',
        bone_lengths_m={f'{p}:{u}-{v}':q for (p,u,v),q in lengths.items()})

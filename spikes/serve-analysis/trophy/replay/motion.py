"""Display-only, zero-phase pose smoothing; measured reconstruction is retained."""
import numpy as np
from scipy.signal import savgol_filter


def _unit(x):
    n=np.linalg.norm(x,axis=-1,keepdims=True)
    return x/np.maximum(n,1e-9)


def smooth_player_motion(frames,fps):
    """Filter contiguous pose runs, stabilize limb lengths, never fill missing people.

    render_joints is intentionally separate from joints: smoothed mannequin motion
    is a presentation layer and cannot replace the reported 3D pose estimates.
    Shorter wrist windows preserve fast swings. Symmetric filtering adds no lag.
    """
    adjustments=[];before=[];after=[];windows={}
    for pid in [0,1]:
        people=[next(p for p in f['players'] if p['id']==pid) for f in frames]
        valid=np.array([p.get('joints') is not None for p in people])
        ids=np.where(valid)[0]
        if not len(ids):continue
        runs=np.split(ids,np.where(np.diff(ids)>1)[0]+1)
        for run in runs:
            raw=np.array([people[i]['joints'] for i in run],float)
            q=raw.copy();root=raw[:,[23,24]].mean(axis=1)
            local=raw-root[:,None]
            def filt(x,count):
                w=min(count,len(run) if len(run)%2 else len(run)-1)
                return savgol_filter(x,w,2,axis=0,mode='interp') if w>=5 else x.copy()
            qroot=filt(root,9)
            for j in range(33):
                w=5 if j in [13,14,15,16,17,18,19,20,21,22] else 7
                q[:,j]=filt(local[:,j],w)+qroot
            # Constant segment lengths remove frame-to-frame stretching. All
            # lengths are robust estimates from this person's measured motion.
            hip_width=np.median(np.linalg.norm(raw[:,24]-raw[:,23],axis=1))
            shoulder_width=np.median(np.linalg.norm(raw[:,12]-raw[:,11],axis=1))
            hip_axis=_unit(q[:,24]-q[:,23]);shoulder_axis=_unit(q[:,12]-q[:,11])
            hips=q[:,[23,24]].mean(axis=1);shoulders=q[:,[11,12]].mean(axis=1)
            spine_length=np.median(np.linalg.norm(raw[:,[11,12]].mean(axis=1)-root,axis=1))
            shoulders=hips+_unit(shoulders-hips)*spine_length
            q[:,23]=hips-hip_axis*hip_width/2;q[:,24]=hips+hip_axis*hip_width/2
            q[:,11]=shoulders-shoulder_axis*shoulder_width/2;q[:,12]=shoulders+shoulder_axis*shoulder_width/2
            for chains in [[(11,13),(12,14)],[(13,15),(14,16)],[(23,25),(24,26)],[(25,27),(26,28)]]:
                length=float(np.median(np.concatenate([np.linalg.norm(raw[:,b]-raw[:,a],axis=1) for a,b in chains])))
                for a,b in chains:q[:,b]=q[:,a]+_unit(q[:,b]-q[:,a])*length
            # Finger/foot detail follows the filtered wrist/ankle without gaps.
            for parent,children in [(15,[17,19,21]),(16,[18,20,22]),(27,[29,31]),(28,[30,32])]:
                for j in children:q[:,j]=q[:,parent]+filt(raw[:,j]-raw[:,parent],7)
            adjustments.extend(np.linalg.norm(q-raw,axis=-1).ravel().tolist())
            if len(run)>2:
                before.extend(np.diff(raw[:,[11,12,13,14,15,16,23,24,25,26,27,28]],n=2,axis=0).ravel())
                after.extend(np.diff(q[:,[11,12,13,14,15,16,23,24,25,26,27,28]],n=2,axis=0).ravel())
            for i,joints in zip(run,q):
                people[i]['render_joints']=joints.tolist()
                people[i]['render_root']=joints[[23,24]].mean(axis=0).tolist()
        windows[str(pid)]={'root':9,'body':7,'arms':5}
    b=float(np.sqrt(np.mean(np.square(before)))) if before else 0
    a=float(np.sqrt(np.mean(np.square(after)))) if after else 0
    return dict(method='symmetric Savitzky-Golay filtering + constant-length limb retargeting',
        scope='render_joints only; raw joints and ball measurements unchanged',fps=fps,
        window_frames=windows,missing_person_frames_filled=False,
        median_joint_adjustment_cm=float(np.median(adjustments)*100) if adjustments else 0,
        p95_joint_adjustment_cm=float(np.percentile(adjustments,95)*100) if adjustments else 0,
        second_difference_rms_m_before=b,second_difference_rms_m_after=a,
        second_difference_rms_reduction_fraction=1-a/b if b else 0)

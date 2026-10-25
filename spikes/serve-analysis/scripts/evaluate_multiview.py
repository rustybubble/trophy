"""Evaluate *already reconstructed* positions against a separate reference file.

Reference data are never inputs to reconstruction. Clock alignment is calibrated
on the first second of reference 2D projections in camera A; spatial error is
reported separately on the remaining, held-out reference time interval.
"""
import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import minimize_scalar
from trophy.replay.multiview import load_camera,project,sample_detections


def evaluate(ball_path,detections_path,reference_path,camera_path,output):
    data=json.loads(Path(ball_path).read_text());balls=data['ball'] if 'ball' in data else [f['ball'] for f in data['frames']]
    rows=json.loads(Path(detections_path).read_text());times=np.array([r['timestamp_seconds'] for r in rows])
    raw=list(csv.DictReader(open(reference_path)))
    # Frame=-1 rows duplicate/interpolate tracking; retain original numbered captures.
    refs={float(r['Timestamp']):[float(r[k]) for k in ['X','Y','Z']] for r in raw if int(r['Frame'])>=0}
    rt=np.array(sorted(refs));rp=np.array([refs[t] for t in rt]);camera=load_camera(camera_path)
    calibration=rt<=rt[0]+1.;uv=project(rp[calibration],camera)
    def clock_cost(origin):
        obs=sample_detections(rows,rt[calibration]-origin)
        errors=[min(100,float(np.linalg.norm(np.array([p['x'],p['y']])-q))) if p else 100 for p,q in zip(obs,uv)]
        return float(np.mean(errors))
    grid=np.arange(rt[0]-3,rt[0]+.5,.002);costs=[clock_cost(x) for x in grid];i=int(np.argmin(costs))
    fit=minimize_scalar(clock_cost,bounds=(grid[max(0,i-1)],grid[min(len(grid)-1,i+1)]),method='bounded');origin=float(fit.x)
    refinterp=interp1d(rt,rp,axis=0,bounds_error=False,fill_value=np.nan)
    records=[]
    for i,(t,b) in enumerate(zip(times,balls)):
        stamp=t+origin;k=int(np.searchsorted(rt,stamp))
        reference_ok=k>0 and k<len(rt) and rt[k]-rt[k-1]<=.025
        gt=refinterp(stamp) if reference_ok else None
        pred=b.get('raw_world_position_m')
        heldout=stamp>rt[0]+1
        error=float(np.linalg.norm(np.array(pred)-gt)) if pred is not None and gt is not None else None
        records.append(dict(frame_index=i,timestamp_seconds=float(t),reference_timestamp_seconds=float(stamp),
            partition='held_out' if heldout else 'clock_alignment',reference_available=bool(reference_ok),
            predicted=pred is not None,error_m=error,reference_position_m=gt.tolist() if gt is not None else None))
    def stats(partition):
        rr=[r for r in records if r['partition']==partition and r['reference_available']]
        es=[r['error_m'] for r in rr if r['error_m'] is not None]
        return dict(reference_frames=len(rr),predicted_frames=len(es),coverage=len(es)/len(rr) if rr else None,
            median_error_cm=float(np.median(es)*100) if es else None,
            mean_error_cm=float(np.mean(es)*100) if es else None,
            p95_error_cm=float(np.percentile(es,95)*100) if es else None,
            max_error_cm=float(np.max(es)*100) if es else None,
            within_5cm=sum(e<=.05 for e in es),within_10cm=sum(e<=.1 for e in es))
    report=dict(reference='official TT3D multi-camera ball tracking',reference_input=str(Path(reference_path).resolve()),
        reference_numbered_rows=len(refs),reference_unnumbered_rows_excluded=sum(int(r['Frame'])<0 for r in raw),
        clock_alignment=dict(reference_time_equals_video_time_plus_seconds=origin,
            method='first 1 second of reference projected to camera A, temporal translation only',
            calibration_2d_mean_clipped_error_px=float(fit.fun),calibration_reference_start_seconds=float(rt[0]),
            calibration_reference_end_seconds=float(rt[0]+1),spatial_calibration_refit=False),
        clock_alignment_partition=stats('clock_alignment'),held_out=stats('held_out'),
        caveats=['Measured on one rally; reference calibration and tracking have their own unknown error.',
                 'Reference clock offset fitted on first second; remaining reference times are held out.',
                 'No reference 3D positions, ball trajectory priors or reference-tuned camera parameters enter reconstruction.',
                 'No human-pose or racket 3D ground truth is provided.'],frames=records)
    Path(output).write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ball',required=True);p.add_argument('--detections',required=True)
    p.add_argument('--reference',required=True);p.add_argument('--camera',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();evaluate(a.ball,a.detections,a.reference,a.camera,a.output)

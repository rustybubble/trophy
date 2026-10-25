"""Continuous public-recording evaluation, separate from selected-window metrics."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from trophy.serves.data import read_samples,read_events
from trophy.serves.inference import predict_frames
from trophy.serves.events import decode_events,evaluate_events
from trophy.serves.model import load_checkpoint
from trophy.serves.attribution import attribute_events


def evaluate(checkpoint,output,videos,device):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    model,metadata,selected=load_checkpoint(checkpoint,device)
    reports=[]
    for video in videos:
        if video in metadata['training']['source_videos_by_split']['train']:
            raise ValueError('Cannot call a training recording held-out evaluation')
        annotation=ROOT/'artifacts/serves-data/annotations/test'/f'{video}.json'
        events=read_events(annotation)
        cache=out/f'{video}-samples.npz'
        if cache.exists():
            data=np.load(cache);images,times=data['images'],data['times']
        else:
            print(f'Decoding continuous {video}',flush=True)
            images,times=read_samples(f'https://lab.osai.ai/datasets/openttgames/data/{video}.mp4',end=max(e['time'] for e in events)+3.)
            np.savez_compressed(cache,images=images,times=times)
        started=time.perf_counter()
        scores=predict_frames(model,images,selected)
        aggregate=metadata.get('event_score_mode')=='serve_sum'
        predicted=decode_events(times,scores,threshold=metadata['threshold'],aggregate_serves=aggregate)
        # Without configured player regions, retain network-side estimates rather
        # than imposing an unvalidated half-frame motion-region assumption.
        truth=[dict(time_seconds=e['time'],player_id='p0' if e['side']=='left' else 'p1') for e in events if e['kind']=='serve']
        occurrence=evaluate_events([dict(e,player_id=None) for e in predicted],[dict(e,player_id=None) for e in truth])
        review=decode_events(times,scores,threshold=metadata.get('review_threshold',metadata['threshold']),aggregate_serves=aggregate)
        review_occurrence=evaluate_events([dict(e,player_id=None) for e in review],[dict(e,player_id=None) for e in truth])
        report=dict(video=video,metrics=evaluate_events(predicted,truth),serve_occurrence_metrics=occurrence,events=predicted,
                    review_metrics=evaluate_events(review,truth),review_occurrence_metrics=review_occurrence,review_events=review,
                    annotations=truth,duration_seconds=float(times[-1]),sampled_frames=len(times),
                    inference_seconds=time.perf_counter()-started,
                    annotation_sha256=hashlib.sha256(annotation.read_bytes()).hexdigest())
        reports.append(report);(out/f'{video}-evaluation.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(dict(video=video,metrics=report['metrics']),indent=2),flush=True)
    counts={key:sum(r['metrics'][key] for r in reports) for key in ['true_positives','false_positives','false_negatives']}
    tp,fp,fn=[counts[k] for k in ['true_positives','false_positives','false_negatives']]
    precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/(tp+fn) if tp+fn else 0.
    occurrence_counts={key:sum(r['serve_occurrence_metrics'][key] for r in reports) for key in ['true_positives','false_positives','false_negatives']}
    otp,ofp,ofn=[occurrence_counts[k] for k in ['true_positives','false_positives','false_negatives']]
    op=otp/(otp+ofp) if otp+ofp else 0.;orr=otp/(otp+ofn) if otp+ofn else 0.
    review_counts={key:sum(r['review_occurrence_metrics'][key] for r in reports) for key in ['true_positives','false_positives','false_negatives']}
    rtp,rfp,rfn=[review_counts[k] for k in ['true_positives','false_positives','false_negatives']]
    rp=rtp/(rtp+rfp) if rtp+rfp else 0.;rr=rtp/(rtp+rfn) if rtp+rfn else 0.
    report=dict(scope='continuous held-out public recordings; baseline test split previously inspected',
                checkpoint_sha256=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),threshold=metadata['threshold'],review_threshold=metadata.get('review_threshold'),
                metrics=dict(counts,precision=precision,recall=recall,
                             f1=2*precision*recall/(precision+recall) if precision+recall else 0.),
                serve_occurrence_metrics=dict(occurrence_counts,precision=op,recall=orr,
                    f1=2*op*orr/(op+orr) if op+orr else 0.),
                review_occurrence_metrics=dict(review_counts,precision=rp,recall=rr,f1=2*rp*rr/(rp+rr) if rp+rr else 0.),recordings=reports)
    (out/'continuous-evaluation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['metrics'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',default='weights/serves/table-tennis-final.pt')
    p.add_argument('--output',default='artifacts/serves/continuous-public')
    p.add_argument('--videos',nargs='+',default=['test_2','test_3','test_6']);p.add_argument('--device',default='auto')
    a=p.parse_args();evaluate(a.checkpoint,a.output,a.videos,a.device)

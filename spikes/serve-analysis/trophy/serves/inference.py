"""Offline overlapping-window inference. Source video is never sent anywhere."""
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from .data import cached_samples, tensor_frames, CLIP_FRAMES, FPS
from .events import decode_events, merge_views
from .model import load_checkpoint, CLASSES
from .attribution import attribute_events


def predict_frames(model, images, device='cpu', stride=24, progress=None):
    if stride < 1 or stride > CLIP_FRAMES:
        raise ValueError('Stride must be between one and the window length')
    n=len(images)
    scores=np.zeros((n,len(CLASSES)),np.float64);weights=np.zeros(n,np.float64)
    if not n:
        return scores
    if n<8:
        scores[:,0]=1.
        return scores
    starts=list(range(0,max(1,n-CLIP_FRAMES+1),stride))
    if n>CLIP_FRAMES and starts[-1] != n-CLIP_FRAMES:
        starts.append(n-CLIP_FRAMES)
    # Edge observations receive support from interior frames of adjacent windows.
    taper=np.maximum(.1,np.hanning(CLIP_FRAMES))
    with torch.inference_mode():
        for i,start in enumerate(starts):
            real=min(CLIP_FRAMES,n-start)
            x=tensor_frames(images[start:start+real],device)
            if real<CLIP_FRAMES:
                x=torch.cat((x,torch.zeros((CLIP_FRAMES-real,*x.shape[1:]),device=device)))
            pred=model(x[None]).softmax(-1)[0,:real].cpu().numpy()
            scores[start:start+real] += pred*taper[:real,None]
            weights[start:start+real] += taper[:real]
            if progress:
                progress(i+1,len(starts))
    if np.any(weights<=0):
        raise RuntimeError('An observed frame received no inference support')
    return scores/weights[:,None]


def analyze_session(config, output, checkpoint, *, device='auto', threshold=None, max_seconds=600., progress=None):
    cfg=json.loads(Path(config).read_text()) if isinstance(config,(str,Path)) else config
    views=cfg.get('views',[])
    if not 1<=len(views)<=2:
        raise ValueError('Configure one or two source views')
    if len({v['id'] for v in views})!=len(views):
        raise ValueError('Configure distinct view IDs')
    if max_seconds <= 0 or not np.isfinite(max_seconds):
        raise ValueError('Maximum duration must be positive and finite')
    out=Path(output)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be new or empty')
    model,metadata,selected=load_checkpoint(checkpoint,device)
    cutoff=float(threshold if threshold is not None else metadata.get('review_threshold',metadata.get('threshold',.5)))
    if not 0<cutoff<1:
        raise ValueError('Score threshold must be between zero and one')
    out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();observations=[];reports=[]
    for view in views:
        video=Path(view['video']).expanduser().resolve()
        if not video.is_file():
            raise ValueError(f'Video unavailable: {video}')
        if progress:progress(view['id'],'Decoding',0,1)
        images,times=cached_samples(video,max_seconds,Path(__file__).resolve().parents[2]/'artifacts/serve-sample-cache')
        def update(done,total):
            if progress:progress(view['id'],'Spotting serves',done,total)
        # A long observation gap must not become adjacent frames in the model.
        scores=np.zeros((len(times),len(CLASSES)))
        segments=np.split(np.arange(len(times)),np.where(np.diff(times)>2.5/FPS)[0]+1)
        for segment in segments:
            scores[segment]=predict_frames(model,images[segment],selected,progress=update)
        mapping=view.get('player_map',{'left':'p0','right':'p1'})
        aggregate=metadata.get('event_score_mode')=='serve_sum'
        events=decode_events(times,scores,threshold=cutoff,player_map=mapping,aggregate_serves=aggregate)
        if aggregate:
            attribute_events(images,times,events,mapping,view.get('player_regions_norm'))
        observations.append(dict(id=view['id'],source_offset_seconds=view.get('source_offset_seconds',0.),events=events))
        # Identity strings are metadata, never filesystem paths.
        index=len(reports)+1
        np.savez_compressed(out/f'view{index}-scores.npz',times=times,scores=scores)
        reports.append(dict(id=view['id'],video=str(video),source_offset_seconds=view.get('source_offset_seconds',0.),
                            source_size_bytes=video.stat().st_size,source_mtime_ns=video.stat().st_mtime_ns,
                            player_map=view.get('player_map',{'left':'p0','right':'p1'}),
                            sampling_fps=FPS,analyzed_until_seconds=float(times[-1]),
                            sampled_frames=len(times),candidates=len(events)))
        del images
    events=merge_views(observations,tolerance=cfg.get('merge_tolerance_seconds',.3),session_id=cfg.get('session_id','session'))
    # A view may observe actor motion even when its event classifier abstains.
    # Keep that identity evidence separate from evidence that a serve occurred.
    unresolved=[e for e in events if e['player_id'] is None and e['review_reason']=='actor_not_observable']
    for view in views:
        missing=[e for e in unresolved if view['id'] not in e['supporting_views']]
        if not missing or not view.get('player_regions_norm'):continue
        images,times=cached_samples(view['video'],max_seconds,Path(__file__).resolve().parents[2]/'artifacts/serve-sample-cache')
        for event in missing:
            source_time=event['time_seconds']+view.get('source_offset_seconds',0.)
            actor=dict(time_seconds=source_time,player_id=None)
            attribute_events(images,times,[actor],view['player_map'],view['player_regions_norm'])
            event.setdefault('attribution_evidence',[]).append(dict(view_id=view['id'],**actor))
        del images
    # Motion in a view that did not recognize the event cannot resolve identity
    # by itself: a receiver may move while the server tosses. Keep it for review.
    for event in events:
        if event['score']<metadata.get('threshold',cutoff):
            event['event_status']='review_needed'
            event['review_reason']='below_strong_evidence_threshold'
    result=dict(schema_version=1,session_id=cfg.get('session_id','session'),
                title=cfg.get('title','Serve review'),players=cfg.get('players',{'p0':'Player 1','p1':'Player 2'}),
                views=reports,events=events,threshold=cutoff,strong_evidence_threshold=metadata.get('threshold',cutoff),device=selected,
                model=dict(path=str(Path(checkpoint).resolve()),sha256=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),
                           format=metadata['format'],training=metadata.get('training'),
                           validation=metadata.get('serve_event_validation',metadata.get('validation'))),
                recorded=True,processing_seconds=time.perf_counter()-started,
                synchronization_status=cfg.get('synchronization_status','user_supplied_offsets_not_independently_verified'),
                limitations=['Event scores are not calibrated probabilities.',
                             'Candidates require review; serve detection is separate from legality.',
                             'Release, toss height and racket impact are not measured by this event model.',
                             'This bidirectional model uses future frames and runs offline.',
                             'Tosses without a striking action are outside the trained contact classes.'])
    (out/'serves.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    with (out/'serves.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['serve_id','time_seconds','player_id','event_status','score','supporting_views','measurement_status'])
        writer.writeheader()
        for e in events:
            writer.writerow({k:','.join(e[k]) if k=='supporting_views' else e[k] for k in writer.fieldnames})
    return result

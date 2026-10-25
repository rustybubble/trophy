"""Pure event decoding, clock mapping, and evaluation (no model dependencies)."""
import hashlib
import math

import numpy as np


def decode_events(times, scores, *, threshold=.5, minimum_separation=.8, player_map=None, aggregate_serves=False):
    times, scores = np.asarray(times, float), np.asarray(scores, float)
    if scores.shape != (len(times), 5) or not np.isfinite(scores).all():
        raise ValueError('Expected finite five-class frame scores')
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('Frame times must be finite and strictly increasing')
    if not 0 < threshold < 1 or minimum_separation <= 0:
        raise ValueError('Invalid decoding thresholds')
    player_map = player_map or {'left':'p0', 'right':'p1'}
    if set(player_map) != {'left', 'right'} or len(set(player_map.values())) != 2:
        raise ValueError('Map left and right to two distinct player IDs')
    candidates = []
    if aggregate_serves:
        # Serve recognition and actor attribution are separate tasks. Two uncertain
        # side predictions can still strongly support that a serving action occurred.
        serve=scores[:,1]+scores[:,2]
        winner=np.stack((scores[:,0],serve,scores[:,3]+scores[:,4]),axis=1).argmax(1)
        indices=np.where((serve>=threshold)&(winner==1))[0]
        if not len(indices):return []
        split=np.where((np.diff(indices)>1)|(np.diff(times[indices])>.15))[0]+1
        for group in np.split(indices,split):
            index=int(group[np.argmax(serve[group])]);label=1+int(scores[index,2]>scores[index,1])
            side='left' if label==1 else 'right'
            candidates.append(dict(time_seconds=float(times[index]),score=float(serve[index]),
                                   player_id=player_map[side],side=side,sampled_frame=index,label=label,
                                   attribution_method='network_side_provisional'))
    winner = scores.argmax(axis=1)
    for label, side in ([] if aggregate_serves else [(1,'left'), (2,'right')]):
        selected = np.where((scores[:, label] >= threshold) & (winner == label))[0]
        if not len(selected):
            continue
        # Separate discontinuities too: a missing interval is not sustained evidence.
        split = np.where((np.diff(selected) > 1) | (np.diff(times[selected]) > .15))[0] + 1
        for group in np.split(selected, split):
            index = int(group[np.argmax(scores[group, label])])
            candidates.append(dict(time_seconds=float(times[index]), score=float(scores[index,label]),
                                   player_id=player_map[side], side=side,
                                   sampled_frame=index, label=label))
    # Competing serve-side peaks at the same instant also suppress one another.
    kept = []
    for event in sorted(candidates, key=lambda e:-e['score']):
        if all(abs(event['time_seconds']-other['time_seconds']) >= minimum_separation for other in kept):
            kept.append(event)
    return sorted(kept, key=lambda e:e['time_seconds'])


def merge_views(views, *, tolerance=.3, session_id='session'):
    """Map source t to session t = source t - source_offset, then fuse once.

    Offsets follow the replay convention: t_source = t_session + offset.
    Same-view events cannot merge. Disagreement about player stays reviewable.
    """
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Invalid cross-view tolerance')
    observations=[]
    ids=set()
    for view in views:
        if view['id'] in ids:
            raise ValueError('View IDs must be unique')
        ids.add(view['id'])
        offset=float(view.get('source_offset_seconds',0))
        if not math.isfinite(offset):
            raise ValueError('Invalid camera offset')
        for event in view['events']:
            t=float(event['time_seconds'])-offset
            if not math.isfinite(t) or not math.isfinite(event['score']):
                raise ValueError('Invalid observation time/score')
            if t < 0:
                continue
            observations.append(dict(event, view_id=view['id'], source_time_seconds=event['time_seconds'],
                                     time_seconds=t))
    groups=[]
    for event in sorted(observations,key=lambda e:e['time_seconds']):
        eligible=[g for g in groups if event['view_id'] not in {e['view_id'] for e in g}
                  and max(abs(event['time_seconds']-e['time_seconds']) for e in g) <= tolerance]
        if eligible:
            group=min(eligible,key=lambda g:abs(np.mean([e['time_seconds'] for e in g])-event['time_seconds']))
            group.append(event)
        else:
            groups.append([event])
    output=[]
    for group in groups:
        best=max(group,key=lambda e:e['score'])
        t=float(np.average([e['time_seconds'] for e in group],weights=[max(e['score'],1e-6) for e in group]))
        conflict=len({e['player_id'] for e in group if e['player_id'] is not None})>1
        known=[e for e in group if e['player_id'] is not None]
        fingerprint='|'.join(f"{e['view_id']}:{e['sampled_frame']}" for e in sorted(group,key=lambda e:e['view_id']))
        event_id=hashlib.sha256(f'{session_id}|{fingerprint}'.encode()).hexdigest()[:16]
        output.append(dict(serve_id=f'{session_id}/serve/{event_id}', time_seconds=t,
                           contact_interval_seconds=[max(0., min(e['time_seconds'] for e in group)-1/15),
                                                     max(e['time_seconds'] for e in group)+1/15],
                           contact_interval_status='sample_resolution_only_not_calibrated_uncertainty',
                           player_id=None if conflict or not known else max(known,key=lambda e:e['score'])['player_id'],
                           event_status='review_needed' if conflict or not known else 'candidate',
                           score=best['score'], score_type='uncalibrated_model_score',
                           supporting_views=[e['view_id'] for e in group],
                           evidence=group, release_interval_seconds=None,
                           measurement_status='release_not_measured', fault_decision=None,
                           review_reason='player_disagreement' if conflict else ('actor_not_observable' if not known else 'model_candidate'), revision=1))
    return sorted(output,key=lambda e:e['time_seconds'])


def evaluate_events(predictions, truth, tolerance=.35):
    """One-to-one event matching; duplicates count as false positives."""
    remaining=set(range(len(truth))); matched=[];false=[]
    for p in sorted(predictions,key=lambda e:-e.get('score',1.)):
        eligible=[i for i in remaining if abs(p['time_seconds']-truth[i]['time_seconds']) <= tolerance
                  and p.get('player_id')==truth[i].get('player_id')]
        if eligible:
            i=min(eligible,key=lambda i:abs(p['time_seconds']-truth[i]['time_seconds']))
            remaining.remove(i);matched.append(abs(p['time_seconds']-truth[i]['time_seconds']))
        else:
            false.append(p)
    tp=len(matched);fp=len(false);fn=len(remaining)
    precision=tp/(tp+fp) if tp+fp else 0.
    recall=tp/(tp+fn) if tp+fn else 0.
    return dict(true_positives=tp,false_positives=fp,false_negatives=fn,
                precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0.,
                mean_timing_error_seconds=float(np.mean(matched)) if matched else None,
                tolerance_seconds=tolerance)

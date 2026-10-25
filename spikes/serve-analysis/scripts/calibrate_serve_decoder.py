"""Select an actor-agnostic serve score threshold on public validation only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from trophy.serves.data import tensor_frames
from trophy.serves.events import decode_events,evaluate_events
from trophy.serves.model import load_checkpoint


def calibrate(checkpoint,manifest,output,device):
    model,data,selected=load_checkpoint(checkpoint,device)
    path=Path(manifest);records=[r for r in json.loads(path.read_text())['records'] if r['split']=='val']
    observations=[]
    with torch.inference_mode():
        for record in records:
            with np.load(path.parent/record['path']) as raw:
                images,times=raw['images'],raw['times']
            scores=model(tensor_frames(images,selected)[None]).softmax(-1)[0].cpu().numpy()
            truth=[dict(time_seconds=e['time'],player_id=None) for e in record['events'] if e['kind']=='serve']
            observations.append((times,scores,truth))
    candidates=[]
    for threshold in np.arange(.2,.91,.025):
        counts=dict(true_positives=0,false_positives=0,false_negatives=0)
        for times,scores,truth in observations:
            predictions=decode_events(times,scores,threshold=float(threshold),aggregate_serves=True)
            for p in predictions:p['player_id']=None
            metrics=evaluate_events(predictions,truth)
            for k in counts:counts[k]+=metrics[k]
        tp,fp,fn=[counts[k] for k in ['true_positives','false_positives','false_negatives']]
        precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/(tp+fn) if tp+fn else 0.
        candidates.append(dict(counts,threshold=float(threshold),precision=precision,recall=recall,
                               f2=5*precision*recall/(4*precision+recall) if precision+recall else 0.))
    best=max(candidates,key=lambda r:(r['f2'],r['precision'],r['threshold']))
    # Human review tolerates more false positives than the strong-evidence tier.
    # Choose its cutoff using only validation: preserve recall with >=80% precision.
    review=min((r for r in candidates if r['recall']>=best['recall'] and r['precision']>=.8),
               key=lambda r:r['threshold'])
    data['threshold']=best['threshold'];data['event_score_mode']='serve_sum'
    data['review_threshold']=review['threshold']
    data['actor_attribution']='observed pre-contact motion, with abstention'
    data['serve_event_validation']=dict(best,review_threshold=review['threshold'],review_metrics=review,
                                        scope='public validation windows, actor-agnostic',
                                        selection='F2 for high-recall review candidates; not calibrated probabilities')
    data['decoder_validation_curve']=candidates
    data['decoder_parent_sha256']=hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest()
    torch.save(data,output)
    Path(output).with_suffix('.report.json').write_text(json.dumps({k:v for k,v in data.items() if k!='state_dict'},indent=2))
    print(json.dumps(best,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',default='weights/serves/table-tennis-adapted.pt')
    p.add_argument('--manifest',default='artifacts/serves-data/adaptation-manifest.json')
    p.add_argument('--output',default='weights/serves/table-tennis-final.pt');p.add_argument('--device',default='auto')
    a=p.parse_args();calibrate(a.checkpoint,a.manifest,a.output,a.device)

"""Train a table-tennis event head using the published temporal visual encoder.

Cache the frozen RegNet/GSM features once, then adapt the bidirectional GRU and
classification head. Validation source videos select threshold/checkpoint; test
source videos are evaluated once after selection. No test data enters updates.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch
from torch import nn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trophy.serves.model import ServeSpotter, select_device, CLASSES
from trophy.serves.data import tensor_frames, frame_targets
from trophy.serves.events import decode_events, evaluate_events


def evaluate(head, samples, device, thresholds):
    values=[]
    head.eval()
    with torch.inference_mode():
        for sample in samples:
            scores=head(torch.from_numpy(sample['features']).to(device)[None])[0].softmax(-1).cpu().numpy()
            truth=[dict(time_seconds=e['time'],player_id='p0' if e['side']=='left' else 'p1')
                   for e in sample['record']['events'] if e['kind']=='serve']
            values.append((sample['times'],scores,truth))
    reports=[]
    for cutoff in thresholds:
        totals=dict(true_positives=0,false_positives=0,false_negatives=0)
        for times,scores,truth in values:
            pred=decode_events(times,scores,threshold=float(cutoff))
            metrics=evaluate_events(pred,truth)
            for key in totals:totals[key]+=metrics[key]
        tp,fp,fn=[totals[k] for k in ['true_positives','false_positives','false_negatives']]
        precision=tp/(tp+fp) if tp+fp else 0.
        recall=tp/(tp+fn) if tp+fn else 0.
        reports.append(dict(totals,threshold=float(cutoff),precision=precision,recall=recall,
                            f1=2*precision*recall/(precision+recall) if precision+recall else 0.,
                            tolerance_seconds=.35,scope='selected_windows_not_continuous_video'))
    return max(reports,key=lambda x:(x['f1'],x['precision'],x['threshold']))


def train(dataset, output, initialization, device='auto', epochs=35, steps=30, learning_rate=.0003):
    selected=select_device(device);torch.manual_seed(24);np.random.seed(24);random.seed(24)
    torch.set_num_threads(4)
    manifest_path=Path(dataset)/'manifest.json'
    manifest_bytes=manifest_path.read_bytes()
    manifest=json.loads(manifest_bytes)
    records=manifest['records']
    if not all(any(r['split']==split for r in records) for split in ['train','val','test']):
        raise ValueError('Training, validation and test source videos are all required')
    videos={}
    for r in records:
        if r['video_id'] in videos and videos[r['video_id']]!=r['split']:
            raise ValueError('A source recording appears in multiple splits')
        videos[r['video_id']]=r['split']
    model=ServeSpotter();init_report=model.initialize(initialization);model.to(selected).eval()
    for p in model._features.parameters():p.requires_grad_(False)
    cache=Path(dataset)/'features';cache.mkdir(exist_ok=True)
    samples=[];start=time.perf_counter()
    init_sha=hashlib.sha256(Path(initialization).read_bytes()).hexdigest()
    for i,record in enumerate(records):
        path=Path(dataset)/record['path']
        source_sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if source_sha!=record['sha256']:raise ValueError(f'Changed training clip: {path}')
        key=hashlib.sha256((source_sha+init_sha+'regnet-gsm-128x224-v1').encode()).hexdigest()[:24]
        target=cache/f'{key}.npz'
        raw=np.load(path)
        images,times=raw['images'],raw['times']
        if not target.exists():
            with torch.inference_mode():features=model.encode(tensor_frames(images,selected)[None])[0].cpu().numpy()
            np.savez_compressed(target,features=features)
        features=np.load(target)['features'].astype(np.float32)
        if len(features)!=len(times):raise ValueError('Feature timestamp mismatch')
        samples.append(dict(features=features,times=times,targets=frame_targets(times,record['events']),record=record))
        if i%20==0 or i+1==len(records):print(f'Encoded {i+1}/{len(records)} windows on {selected}',flush=True)
    groups={split:[s for s in samples if s['record']['split']==split] for split in ['train','val','test']}
    head=model._pred_fine
    optimizer=torch.optim.AdamW(head.parameters(),lr=learning_rate,weight_decay=.01)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,epochs)
    # Event-label dilation represents a training tolerance, not a measured interval.
    criterion=nn.CrossEntropyLoss(weight=torch.tensor([1.,8.,8.,3.,3.],device=selected),ignore_index=-100)
    best=None;history=[];thresholds=np.arange(.15,.86,.05)
    train_samples=groups['train']
    for epoch in range(epochs):
        head.train();loss_sum=0.
        for step in range(steps):
            batch=random.choices(train_samples,k=8)
            length=max(len(s['features']) for s in batch)
            x=np.zeros((len(batch),length,batch[0]['features'].shape[1]),np.float32)
            y=np.full((len(batch),length),-100,np.int64)
            for j,sample in enumerate(batch):
                n=len(sample['features']);x[j,:n]=sample['features'];y[j,:n]=sample['targets']
            xt=torch.from_numpy(x).to(selected);yt=torch.from_numpy(y).to(selected)
            # Mild feature dropout trains robustness without hallucinating ball observations.
            xt=nn.functional.dropout(xt,p=.1,training=True)
            optimizer.zero_grad(set_to_none=True)
            logits=head(xt)
            loss=criterion(logits.reshape(-1,len(CLASSES)),yt.flatten())
            loss.backward();nn.utils.clip_grad_norm_(head.parameters(),1.)
            optimizer.step();loss_sum+=float(loss.detach().cpu())
        scheduler.step()
        val=evaluate(head,groups['val'],selected,thresholds)
        history.append(dict(epoch=epoch+1,loss=loss_sum/steps,validation=val))
        if best is None or (val['f1'],val['precision'])>(best['metrics']['f1'],best['metrics']['precision']):
            best=dict(metrics=val,state={k:v.detach().cpu().clone() for k,v in head.state_dict().items()},epoch=epoch+1)
        print(f"Epoch {epoch+1}/{epochs}: loss={loss_sum/steps:.4f} val F1={val['f1']:.3f} P={val['precision']:.3f} R={val['recall']:.3f} threshold={val['threshold']:.2f}",flush=True)
    head.load_state_dict(best['state']);head.eval()
    test=evaluate(head,groups['test'],selected,[best['metrics']['threshold']])
    training=dict(dataset=manifest.get('dataset','custom'),manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                  source_videos_by_split={k:sorted({s['record']['video_id'] for s in v}) for k,v in groups.items()},
                  windows_by_split={k:len(v) for k,v in groups.items()},
                  selected_epoch=best['epoch'],epochs=epochs,steps_per_epoch=steps,
                  initialization_sha256=init_sha,initialization=init_report,visual_encoder_frozen=True,
                  label_dilation_seconds=.14,device=selected,seed=24,
                  seconds=time.perf_counter()-start,data_license=manifest.get('license'))
    checkpoint=dict(format='trophy-serve-spotter-v1',classes=CLASSES,
                    state_dict={k:v.detach().cpu() for k,v in model.state_dict().items()},
                    threshold=best['metrics']['threshold'],training=training,
                    validation=best['metrics'],test=test)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    torch.save(checkpoint,output)
    report=dict(training=training,validation=best['metrics'],test=test,history=history)
    output.with_suffix('.report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(dict(checkpoint=str(output),validation=best['metrics'],test=test),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='artifacts/serves-data')
    p.add_argument('--output',default='weights/serves/table-tennis.pt')
    p.add_argument('--initialization',default='weights/serves/tennis-initialization.pt')
    p.add_argument('--device',default='auto',choices=['auto','cpu','mps','cuda'])
    p.add_argument('--epochs',type=int,default=35);p.add_argument('--steps',type=int,default=30)
    a=p.parse_args();train(a.dataset,a.output,a.initialization,a.device,a.epochs,a.steps)

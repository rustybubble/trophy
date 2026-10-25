"""Adapt the visual encoder as well as the event head, using training splits only."""
import argparse
from functools import lru_cache
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
sys.path.insert(0,str(ROOT/'scripts'))
from trophy.serves.model import load_checkpoint,CLASSES
from trophy.serves.data import tensor_frames,frame_targets
from train_serve_spotter import evaluate


def finetune(dataset,manifest_path,initialization,output,epochs=10,steps=25,device='auto'):
    torch.manual_seed(42);np.random.seed(42);random.seed(42);torch.set_num_threads(4)
    root=Path(dataset);manifest_bytes=Path(manifest_path).read_bytes();manifest=json.loads(manifest_bytes)
    records=manifest['records'];groups={s:[r for r in records if r['split']==s] for s in ['train','val','test']}
    if any(not group for group in groups.values()):raise ValueError('All recording splits are required')
    split_by_video={}
    for r in records:
        if r['video_id'] in split_by_video and split_by_video[r['video_id']]!=r['split']:
            raise ValueError('Source recording leakage across splits')
        split_by_video[r['video_id']]=r['split']
    model,previous,selected=load_checkpoint(initialization,device)
    for parameter in model.parameters():parameter.requires_grad_(True)
    @lru_cache(maxsize=40)
    def read(path):
        with np.load(root/path) as data:return data['images'],data['times']
    # Check every asset before training; feature caches cannot hide changed clips.
    for record in records:
        if hashlib.sha256((root/record['path']).read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Training clip differs from its manifest')
    public=[r for r in groups['train'] if not r['video_id'].startswith('room-')]
    local=[r for r in groups['train'] if r['video_id'].startswith('room-')]
    optimizer=torch.optim.AdamW([
        dict(params=model._features.parameters(),lr=3e-5),
        dict(params=model._pred_fine.parameters(),lr=1e-4)],weight_decay=.01)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,epochs)
    criterion=nn.CrossEntropyLoss(weight=torch.tensor([1.,8.,8.,3.,3.],device=selected),ignore_index=-100)
    thresholds=np.arange(.15,.91,.05);best=None;history=[];started=time.perf_counter()

    def assess(record_group,cutoffs):
        samples=[];model.eval()
        with torch.inference_mode():
            for record in record_group:
                images,times=read(record['path'])
                features=model.encode(tensor_frames(images,selected)[None])[0].cpu().numpy()
                samples.append(dict(features=features,times=times,record=record))
        return evaluate(model._pred_fine,samples,selected,cutoffs)

    for epoch in range(epochs):
        model.train()
        # Keep pretrained normalization stable with two independent clips/batch.
        for module in model.modules():
            if isinstance(module,(nn.BatchNorm1d,nn.BatchNorm2d,nn.BatchNorm3d)):module.eval()
        loss_sum=0.
        for step in range(steps):
            batch=[random.choice(local if local and random.random()<.35 else public) for _ in range(2)]
            raw=[read(r['path']) for r in batch];length=max(len(x[0]) for x in raw)
            inputs=[];targets=[]
            for record,(images,times) in zip(batch,raw):
                x=tensor_frames(images,selected);y=torch.from_numpy(frame_targets(times,record['events'])).to(selected)
                if random.random()<.5:
                    x=x.flip(-1);swap=y.clone();swap[y==1]=2;swap[y==2]=1;swap[y==3]=4;swap[y==4]=3;y=swap
                # Shared color changes across each clip preserve its temporal motion.
                x=x*torch.empty((1,3,1,1),device=selected).uniform_(.8,1.2)
                x=x+torch.empty((1,3,1,1),device=selected).uniform_(-.15,.15)
                if len(x)<length:
                    x=torch.cat((x,torch.zeros((length-len(x),*x.shape[1:]),device=selected)))
                    y=nn.functional.pad(y,(0,length-len(y)),value=-100)
                inputs.append(x);targets.append(y)
            optimizer.zero_grad(set_to_none=True)
            pred=model(torch.stack(inputs));loss=criterion(pred.reshape(-1,len(CLASSES)),torch.stack(targets).flatten())
            loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
            loss_sum+=float(loss.detach().cpu())
        scheduler.step();val=assess(groups['val'],thresholds)
        history.append(dict(epoch=epoch+1,loss=loss_sum/steps,validation=val))
        if best is None or (val['f1'],val['precision'])>(best['metrics']['f1'],best['metrics']['precision']):
            best=dict(metrics=val,epoch=epoch+1,state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()})
        print(f"Joint epoch {epoch+1}/{epochs}: loss={loss_sum/steps:.3f} val F1={val['f1']:.3f} P={val['precision']:.3f} R={val['recall']:.3f}",flush=True)
    model.load_state_dict(best['state']);model.eval()
    test=assess(groups['test'],[best['metrics']['threshold']])
    training=dict(dataset=manifest['dataset'],manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                  source_videos_by_split={k:sorted({r['video_id'] for r in v}) for k,v in groups.items()},
                  windows_by_split={k:len(v) for k,v in groups.items()},selected_epoch=best['epoch'],
                  epochs=epochs,steps_per_epoch=steps,visual_encoder_frozen=False,device=selected,
                  initialization_sha256=hashlib.sha256(Path(initialization).read_bytes()).hexdigest(),
                  seconds=time.perf_counter()-started,local_training_interval_seconds=manifest.get('local_training_interval_seconds'),
                  local_holdout_interval_seconds=manifest.get('local_holdout_interval_seconds'),
                  seed=42,data_license=manifest.get('license'))
    checkpoint=dict(format='trophy-serve-spotter-v1',classes=CLASSES,state_dict=best['state'],
                    threshold=best['metrics']['threshold'],training=training,validation=best['metrics'],test=test)
    output=Path(output);output.parent.mkdir(exist_ok=True,parents=True);torch.save(checkpoint,output)
    output.with_suffix('.report.json').write_text(json.dumps(dict(training=training,validation=best['metrics'],test=test,history=history),indent=2))
    print(json.dumps(dict(checkpoint=str(output),validation=best['metrics'],test=test),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='artifacts/serves-data')
    p.add_argument('--manifest',default='artifacts/serves-data/manifest.json')
    p.add_argument('--initialization',default='weights/serves/table-tennis.pt')
    p.add_argument('--output',default='weights/serves/table-tennis-adapted.pt')
    p.add_argument('--epochs',type=int,default=10);p.add_argument('--steps',type=int,default=25)
    p.add_argument('--device',default='auto');a=p.parse_args()
    finetune(a.dataset,a.manifest,a.initialization,a.output,a.epochs,a.steps,a.device)

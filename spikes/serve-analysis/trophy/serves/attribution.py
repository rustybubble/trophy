"""Attribute a detected serving action from observed pre-contact player motion.

The video event head decides whether a serve occurred. Actor identity is estimated
separately, avoiding dependence on its unreliable left/right class split under a
new viewpoint. Optical-flow evidence is an estimate, not measured racket contact.
"""
import cv2
import numpy as np


def attribute_events(images,times,events,player_map,regions=None,minimum_ratio=1.3):
    regions=regions or {'left':[0.,.15,.5,1.], 'right':[.5,.15,1.,1.]}
    if set(regions)!={'left','right'}:raise ValueError('Configure two player motion regions')
    h,w=images.shape[1:3]
    boxes={}
    background=np.ones((h,w),bool)
    for side,box in regions.items():
        if len(box)!=4 or not (0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1):
            raise ValueError('Motion regions must be normalized, ordered image boxes')
        x0,y0,x1,y1=[round(v*n) for v,n in zip(box,[w,h,w,h])]
        if x1-x0<4 or y1-y0<4:raise ValueError('Motion region is too small')
        boxes[side]=(x0,y0,x1,y1);background[y0:y1,x0:x1]=False
    flows={}
    for event in events:
        indices=np.where((times>=event['time_seconds']-1.3)&(times<=event['time_seconds']+.067))[0]
        energy={side:[] for side in boxes}
        for index in indices:
            if index==0 or times[index]-times[index-1]>.15:continue
            if index not in flows:
                a=cv2.cvtColor(images[index-1],cv2.COLOR_RGB2GRAY)
                b=cv2.cvtColor(images[index],cv2.COLOR_RGB2GRAY)
                flow=cv2.calcOpticalFlowFarneback(a,b,None,.5,3,13,3,5,1.2,0)
                # Remove dominant background translation before comparing players.
                offset=np.median(flow[background],axis=0) if background.sum()>20 else np.median(flow.reshape(-1,2),axis=0)
                flows[index]=flow-offset
            flow=flows[index]
            for side,(x0,y0,x1,y1) in boxes.items():
                magnitude=np.linalg.norm(flow[y0:y1,x0:x1],axis=2)
                top=magnitude[magnitude>=np.percentile(magnitude,90)]
                energy[side].append(float(top.mean()/np.hypot(x1-x0,y1-y0)))
        values={side:float(np.mean(v)) if v else 0. for side,v in energy.items()}
        ordered=sorted(values,key=values.get,reverse=True);first,second=ordered
        ratio=values[first]/max(values[second],1e-8)
        event['network_player_id']=event['player_id']
        event['motion_evidence']=dict(energy=values,dominance_ratio=ratio,
                                      interval_seconds=[max(0.,event['time_seconds']-1.3),event['time_seconds']+.067])
        event['attribution_method']='pre_contact_motion_estimate'
        event['player_id']=player_map[first] if ratio>=minimum_ratio and values[first]>.0005 else None
    return events

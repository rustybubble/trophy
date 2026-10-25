"""Render the same exported 3D motion to browser-playable MP4, entirely locally."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from trophy.pipeline import Encoder,verify_video
from trophy.replay.solid import body_mesh,box_mesh,render_triangles,racket_mesh
from trophy.replay.avatar import avatar_triangles

EDGES=[(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),(23,24),(23,25),(25,27),(24,26),(26,28),(27,31),(28,32)]
COLORS=[(255,192,112),(112,170,255)]

def look_at(position,target):
    forward=np.array(target,float)-position;forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0,0,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    return np.array([right,-up,forward])


def render_frame(scene,index,view='courtside',phase=0,width=1280,height=720,timestamp=None):
    if view=='overhead':pos=np.array([.01,-.01,7.8]);target=[0,0,.6]
    elif view=='orbit':pos=np.array([6*np.sin(phase+.7),-6*np.cos(phase+.7),3.5]);target=[0,0,.8]
    else:pos=np.array([4.5,-5.8,3.3]);target=[0,0,.8]
    R=look_at(pos,target);focal=800
    def px(p):
        q=R@(np.array(p)-pos)
        if q[2]<=.1:return None
        return tuple(np.rint([width/2+focal*q[0]/q[2],height*.51+focal*q[1]/q[2]]).astype(int))
    image=np.full((height,width,3),(31,24,17),np.uint8)
    def line(a,b,color,thick=1):
        x,y=px(a),px(b)
        if x is not None and y is not None:cv2.line(image,x,y,color,thick,cv2.LINE_AA)
    for i in np.arange(-6,6.1,.5):
        line([i,-5,0],[i,5,0],(54,45,34));line([-6,i,0],[6,i,0],(54,45,34))
    for x in [-1.02,1.02]:
        for y in [-.53,.53]:line([x,y,.72],[x,y,0],(133,117,100),7)
    corners=[[-1.37,-.7625,.76],[1.37,-.7625,.76],[1.37,.7625,.76],[-1.37,.7625,.76]]
    pts=np.array([px(p) for p in corners]);cv2.fillConvexPoly(image,pts,(104,102,39),cv2.LINE_AA)
    for a,b in zip(corners,corners[1:]+corners[:1]):line(a,b,(218,230,227),2)
    line([-1.37,0,.762],[1.37,0,.762],(218,230,227),1)
    for y in np.linspace(-.7625,.7625,20):line([0,y,.76],[0,y,.9125],(155,165,160))
    for z in np.linspace(.76,.9125,5):line([0,-.7625,z],[0,.7625,z],(155,165,160))
    frame=scene['frames'][index]
    if scene.get('continuous_avatars') and timestamp is not None and index+1<len(scene['frames']):
        # Interpolate only display poses between valid neighboring frames.
        # Ball positions and detection status remain the source observations.
        following=scene['frames'][index+1];span=following['time']-frame['time']
        u=np.clip((timestamp-frame['time'])/span,0,1) if span>0 else 0
        people=[]
        for person in frame['players']:
            next_person=next((p for p in following['players'] if p['id']==person['id']),None)
            if person.get('render_joints') and next_person and next_person.get('render_joints'):
                q=(1-u)*np.array(person['render_joints'])+u*np.array(next_person['render_joints'])
                people.append({**person,'render_joints':q.tolist()})
            else:people.append(person)
        frame={**frame,'players':people}
    if scene.get('multiview'):
        triangles=box_mesh([0,0,.7325],[2.74,1.525,.055],[104,102,39])
        for x in [-1.02,1.02]:
            for y in [-.53,.53]:triangles+=box_mesh([x,y,.35],[.05,.05,.7],[133,117,100])
        for person in frame['players']:
            if scene.get('continuous_avatars'):
                triangles+=avatar_triangles(person)
                if person.get('joints'):
                    triangles+=racket_mesh(np.array(person.get('render_joints',person['joints'])),person['id'])
            else:triangles+=body_mesh(person)
        render_triangles(image,triangles,pos,R,focal)
    people=sorted(frame['players'],key=lambda p: np.linalg.norm(np.array(p['root'])-pos) if p.get('root') else 0,reverse=True)
    for person in people:
        if scene.get('multiview'):continue
        if person['joints'] is None:continue
        joints=np.array(person['joints']);color=COLORS[person['id']]
        for a,b in EDGES:
            c=tuple(int(v*.45) for v in color) if person.get('leg_pose_prior') and a in [23,24,25,26,27,28] and b!=24 else color
            line(joints[a],joints[b],c,8)
        for j in [11,12,13,14,15,16,23,24,25,26,27,28]:
            point=px(joints[j]);
            if point is not None:cv2.circle(image,point,5,color,-1,cv2.LINE_AA)
        head=px(joints[0]+[0,0,.025])
        if head is not None:cv2.circle(image,head,12,color,-1,cv2.LINE_AA)
    for j in range(max(0,index-16),index):
        a,b=scene['frames'][j]['ball']['position'],scene['frames'][j+1]['ball']['position']
        if a is not None and b is not None:line(a,b,(145,224,186),2)
    bp=px(frame['ball']['position']) if frame['ball']['position'] is not None else None
    if bp is not None:
        color=(245,250,250) if frame['ball']['observed_2d'] else (90,190,245)
        cv2.circle(image,bp,6,(54,72,65),-1,cv2.LINE_AA);cv2.circle(image,bp,4,color,-1,cv2.LINE_AA)
    cv2.putText(image,'TROPHY / 3D REPLAY',(38,40),cv2.FONT_HERSHEY_SIMPLEX,.7,(224,237,237),1,cv2.LINE_AA)
    cv2.putText(image,f'{view.upper()}    {frame["time"]:.2f}s   Frame {index}',(38,68),cv2.FONT_HERSHEY_SIMPLEX,.45,(150,180,190),1,cv2.LINE_AA)
    label='TWO-CAMERA RECONSTRUCTION | Ball triangulated; hidden joints estimated' if scene.get('multiview') else 'SINGLE-CAMERA ESTIMATE | Depth & hidden joints inferred'
    note='Rackets follow wrists; racket-face orientation is illustrative' if scene.get('multiview') else 'Dim legs: neutral stance prior during occlusion'
    cv2.putText(image,label,(38,height-40),cv2.FONT_HERSHEY_SIMPLEX,.5,(125,190,225),1,cv2.LINE_AA)
    cv2.putText(image,note,(38,height-20),cv2.FONT_HERSHEY_SIMPLEX,.4,(130,155,165),1,cv2.LINE_AA)
    return image


def render(path,output,view,fps=30):
    scene=json.loads(Path(path).read_text());times=np.array([f['time'] for f in scene['frames']]);n=max(1,int(np.ceil((scene['duration']+1/scene['fps'])*fps)))
    enc=Encoder(output,1280,720,fps)
    try:
        for i in range(n):
            t=min(i/fps,scene['duration']);index=max(0,int(np.searchsorted(times,t,side='right')-1))
            enc.write(render_frame(scene,index,view,phase=2*np.pi*i/n,timestamp=t))
        enc.close()
    except Exception:
        if not enc.log.closed:enc.abort()
        raise
    print(json.dumps(verify_video(output,n,fps)))
    return scene

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('scene');p.add_argument('--output',required=True)
    p.add_argument('--view',choices=['orbit','overhead','courtside'],default='orbit');p.add_argument('--fps',type=float,default=30)
    a=p.parse_args();render(a.scene,a.output,a.view,a.fps)

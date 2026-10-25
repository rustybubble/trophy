"""Continuous procedural human surface with blended skeletal deformation.

The same rest mesh and skin weights drive WebGL and offline export. No body
segments are disconnected. This is a mannequin, not recovered human anatomy.
"""
import json
from functools import lru_cache
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def rest_joints():
    q=np.zeros((33,3));q[:,2]=1.65;q[0]=[0,-.08,1.615]
    for j,p in {11:[-.19,0,1.43],12:[.19,0,1.43],13:[-.38,0,1.20],14:[.38,0,1.20],
        15:[-.54,-.015,1.02],16:[.54,-.015,1.02],23:[-.095,0,.91],24:[.095,0,.91],
        25:[-.12,.015,.49],26:[.12,.015,.49],27:[-.12,0,.085],28:[.12,0,.085],
        31:[-.12,-.14,.045],32:[.12,-.14,.045]}.items():q[j]=p
    return q


def unit(v):return np.asarray(v)/max(1e-10,np.linalg.norm(v))


def rotation_from_y(direction):
    v=unit(direction);c=v[1]
    if c<-.999999:return np.diag([1.,-1.,-1.])
    x=np.cross([0,1.,0],v);K=np.array([[0,-x[2],x[1]],[x[2],0,-x[0]],[-x[1],x[0],0]])
    return np.eye(3)+K+K@K/max(1e-9,1+c)


def bone_endpoints(q):
    q=np.asarray(q);hips=q[[23,24]].mean(axis=0);shoulders=q[[11,12]].mean(axis=0)
    up=unit(shoulders-hips);side=unit(q[12]-q[11]);front=unit(np.cross(side,up))
    head=q[0]-.08*front+.035*up
    # Landmark 0 is the nose, not the head centre. Retarget its direction to
    # a plausible mannequin neck rather than stretching the surface to it.
    delta=head-shoulders
    head=shoulders+unit(delta)*np.clip(np.linalg.norm(delta),.20,.27)
    pairs=[(hips,shoulders),(shoulders,head),(head-up*.13,head+up*.13)]
    for shoulder,elbow,wrist in [(11,13,15),(12,14,16)]:
        pairs.extend([(q[shoulder],q[elbow]),(q[elbow],q[wrist]),(q[wrist],q[wrist]+unit(q[wrist]-q[elbow])*.095)])
    for hip,knee,ankle,toe in [(23,25,27,31),(24,26,28,32)]:
        pairs.extend([(q[hip],q[knee]),(q[knee],q[ankle]),(q[ankle],q[toe])])
    return np.asarray(pairs)


@lru_cache(maxsize=2)
def load_avatar(lod='low'):
    d=json.loads((ROOT/f'web/multiview/avatar-{lod}.json').read_text())
    return {k:np.asarray(d[k]) for k in ['positions','normals','faces','skin_indices','skin_weights','bones']}


def deform(q,asset):
    endpoints=bone_endpoints(q);vertices=asset['positions'];normals=asset['normals']
    xyz=np.zeros_like(vertices,dtype=float);nn=np.zeros_like(normals,dtype=float)
    for k,(rest,target) in enumerate(zip(asset['bones'],endpoints)):
        ra,rb=rest;ta,tb=target;rr=rotation_from_y(rb-ra);rt=rotation_from_y(tb-ta)
        scale=np.diag([1,np.linalg.norm(tb-ta)/max(1e-9,np.linalg.norm(rb-ra)),1])
        matrix=rt@scale@rr.T
        w=np.sum(np.where(asset['skin_indices']==k,asset['skin_weights'],0),axis=1)
        xyz+=((vertices-ra)@matrix.T+ta)*w[:,None]
        nn+=(normals@np.linalg.inv(matrix).copy())*w[:,None]
    nn/=np.maximum(1e-9,np.linalg.norm(nn,axis=1,keepdims=True))
    return xyz,nn


def avatar_triangles(person,lod='low'):
    if not person.get('joints'):return []
    asset=load_avatar(lod);q=np.array(person.get('render_joints',person['joints']))
    xyz,normals=deform(q,asset)
    color=np.array([255,186,103]) if person['id']==0 else np.array([110,163,255])
    return [(xyz[f],color,normals[f]) for f in asset['faces']]

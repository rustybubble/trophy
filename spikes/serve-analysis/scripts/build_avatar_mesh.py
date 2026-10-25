"""Generate a single watertight human surface by smooth implicit union.

Asset-generation dependency only: scikit-image==0.25.2. Checked-in JSON assets
need only NumPy at runtime. No downloaded character or body-model licence.
"""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from skimage.measure import marching_cubes
from trophy.replay.avatar import bone_endpoints,rest_joints


def smooth_min(a,b,k=.045):
    h=np.clip(.5+.5*(b-a)/k,0,1)
    return b*(1-h)+a*h-k*h*(1-h)


def capsule(p,a,b,r0,r1=None):
    d=b-a;t=np.clip(((p-a)@d)/np.dot(d,d),0,1)
    return np.linalg.norm(p-a-t[:,None]*d,axis=1)-(r0 if r1 is None else r0+(r1-r0)*t)


def ellipsoid(p,center,radii):
    q=(p-center)/radii;k0=np.linalg.norm(q,axis=1);k1=np.linalg.norm(q/radii,axis=1)
    return k0*(k0-1)/np.maximum(k1,1e-8)


def fields(p,bones):
    torso=smooth_min(ellipsoid(p,[0,0,1.205],[.205,.115,.285]),ellipsoid(p,[0,0,.945],[.175,.12,.14]))
    values=[torso,capsule(p,*bones[1],.063),ellipsoid(p,[0,0,1.65],[.101,.105,.135])]
    for offset in [3,6]:
        values.extend([capsule(p,*bones[offset],.074,.056),capsule(p,*bones[offset+1],.056,.036),capsule(p,*bones[offset+2],.038,.032)])
    for offset in [9,12]:
        values.extend([capsule(p,*bones[offset],.095,.073),capsule(p,*bones[offset+1],.071,.042),
            ellipsoid(p,[bones[offset+2,0,0],-.065,.052],[.061,.125,.052])])
    return np.stack(values,axis=1)


def generate(spacing,lod):
    minimum=np.array([-.72,-.25,-.04]);maximum=np.array([.72,.24,1.86])
    axes=[np.arange(a,b+spacing,spacing) for a,b in zip(minimum,maximum)]
    p=np.stack(np.meshgrid(*axes,indexing='ij'),axis=-1).reshape(-1,3);bones=bone_endpoints(rest_joints())
    ff=fields(p,bones);sdf=ff[:,0]
    for i in range(1,len(bones)):sdf=smooth_min(sdf,ff[:,i])
    v,f,_,_=marching_cubes(sdf.reshape(*[len(a) for a in axes]),0,spacing=(spacing,)*3,gradient_direction='ascent',allow_degenerate=False)
    v+=minimum
    # Smooth area-weighted normals, shared across the connected indexed surface.
    n=np.zeros_like(v);face_n=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    for i in range(3):np.add.at(n,f[:,i],face_n)
    n/=np.maximum(1e-9,np.linalg.norm(n,axis=1,keepdims=True))
    ff=fields(v,bones);indices=np.argsort(ff,axis=1)[:,:4];chosen=np.take_along_axis(ff,indices,axis=1)
    weights=np.exp(-(chosen-chosen[:,:1])/.032);weights/=weights.sum(axis=1,keepdims=True)
    output=dict(schema_version=1,kind='single connected smooth-union human surface',
        units='metres',positions=v.round(6).tolist(),normals=n.round(6).tolist(),faces=f.tolist(),
        skin_indices=indices.tolist(),skin_weights=weights.round(7).tolist(),bones=bones.tolist())
    path=Path(f'web/multiview/avatar-{lod}.json');path.write_text(json.dumps(output,separators=(',',':')))
    print(path,len(v),'vertices',len(f),'faces',flush=True)

if __name__=='__main__':
    generate(.021,'high');generate(.042,'low')

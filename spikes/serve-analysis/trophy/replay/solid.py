"""Small local solid-mesh renderer shared by the offline MP4 export.

Uses the same measured joints and wrist-attached racket convention as WebGL.
Depth-sorted shaded triangles provide solid human silhouettes without Blender,
external character assets, motion templates, or a learned body-shape claim.
"""
import numpy as np

SKIN=np.array([172,194,217]);SHIRT=[np.array([255,186,103]),np.array([110,163,255])]
PANTS=np.array([75,58,41]);SHOES=np.array([240,237,228])


def unit(x):
    return np.asarray(x)/max(1e-10,np.linalg.norm(x))


def basis_y(direction):
    y=unit(direction);helper=np.array([0.,0,1.]) if abs(y[2])<.9 else np.array([1.,0,0])
    x=unit(np.cross(y,helper));z=np.cross(x,y);return np.array([x,y,z]).T


def ellipsoid(center,scale,basis,color,rings=8,slices=12):
    pts=[]
    for a in np.linspace(0,np.pi,rings+1):
        for b in np.linspace(0,2*np.pi,slices,endpoint=False):pts.append([np.sin(a)*np.cos(b),np.sin(a)*np.sin(b),np.cos(a)])
    pts=np.array(pts)*scale;pts=pts@basis.T+center;tri=[]
    for i in range(rings):
        for j in range(slices):
            a=i*slices+j;b=i*slices+(j+1)%slices;c=(i+1)*slices+j;d=(i+1)*slices+(j+1)%slices
            tri.extend([(pts[[a,c,b]],color),(pts[[b,c,d]],color)])
    return tri


def body_mesh(person):
    if not person.get('joints'):return []
    q=np.array(person.get('render_joints',person['joints']));pid=person['id'];color=SHIRT[pid];out=[]
    shoulder=q[[11,12]].mean(axis=0);hips=q[[23,24]].mean(axis=0);up=unit(shoulder-hips)
    side=unit(q[12]-q[11]);front=unit(np.cross(side,up));basis=np.array([side,front,up]).T
    out+=ellipsoid(hips*.45+shoulder*.55,[max(.17,np.linalg.norm(q[11]-q[12])*.58),.125,max(.2,np.linalg.norm(shoulder-hips)*.58)],basis,color)
    out+=ellipsoid(hips,[.17,.12,.12],basis,PANTS)
    head=q[0]-.045*front+[0,0,.035];out+=ellipsoid(head,[.105,.105,.14],basis,SKIN)
    specs=[(11,13,.064,color),(13,15,.052,SKIN),(12,14,.064,color),(14,16,.052,SKIN),
           (23,25,.091,PANTS),(25,27,.066,SKIN),(24,26,.091,PANTS),(26,28,.066,SKIN)]
    for a,b,r,c in specs:
        out+=ellipsoid((q[a]+q[b])/2,[r,np.linalg.norm(q[b]-q[a])/2+r*.25,r],basis_y(q[b]-q[a]),c,rings=6,slices=10)
    for j in [15,16]:out+=ellipsoid(q[j],[.045,.035,.06],basis,SKIN,rings=5,slices=8)
    out+=ellipsoid((shoulder+head-[0,0,.1])/2,[.055,.055,.08],basis,SKIN,rings=5,slices=8)
    for a,b in [(27,31),(28,32)]:
        center=.55*q[a]+.45*q[b];center[2]=max(.045,center[2]-.035)
        out+=ellipsoid(center,[.062,.13,.045],basis_y(q[b]-q[a]),SHOES,rings=5,slices=10)
    return out+racket_mesh(q,pid)


def racket_mesh(q,pid):
    """Independent prop; the player's continuous body has no separate parts."""
    out=[];up=unit(q[[11,12]].mean(axis=0)-q[[23,24]].mean(axis=0))
    front=unit(np.cross(q[12]-q[11],up))
    # Paddle face lies in the handle/forearm plane. Its twist is illustrative.
    direction=unit(q[16]-q[14]);normal=unit(np.cross(direction,up))
    if np.linalg.norm(normal)<.1:normal=front
    lateral=unit(np.cross(direction,normal));racket_basis=np.array([lateral,normal,direction]).T
    out+=ellipsoid(q[16]+direction*.042,[.014,.014,.055],racket_basis,np.array([85,139,180]),rings=5,slices=8)
    out+=ellipsoid(q[16]+direction*.17,[.076,.007,.087],racket_basis,np.array([80,72,215]) if pid==0 else np.array([38,35,34]),rings=6,slices=16)
    return out


def box_mesh(center,size,color):
    corners=np.array([[x,y,z] for x in [-1,1] for y in [-1,1] for z in [-1,1]])*np.array(size)/2+center
    faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
    return [(corners[list(ids)],np.array(color)) for a,b,c,d in faces for ids in [(a,b,c),(a,c,d)]]


def render_triangles(image,triangles,camera_position,R,focal):
    import cv2
    h,w=image.shape[:2];light=unit(np.array([-3.,-4,8]));depth=np.full((h,w),np.inf)
    for triangle in triangles:
        pts,color=triangle[:2]
        camera=(pts-camera_position)@R.T
        if camera[:,2].min()<=.1:continue
        uv=np.c_[w/2+focal*camera[:,0]/camera[:,2],h*.51+focal*camera[:,1]/camera[:,2]]
        n=unit(np.cross(pts[1]-pts[0],pts[2]-pts[0]));shade=.48+.52*abs(n@light)
        smooth_shade=.48+.52*np.abs(np.asarray(triangle[2])@light) if len(triangle)>2 else None
        x0,y0=np.maximum(0,np.floor(uv.min(axis=0)).astype(int));x1,y1=np.minimum([w-1,h-1],np.ceil(uv.max(axis=0)).astype(int))
        if x1<x0 or y1<y0:continue
        a,b,c=uv;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-8:continue
        xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
        wa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
        wb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;wc=1-wa-wb
        z=1/np.maximum(1e-10,wa/camera[0,2]+wb/camera[1,2]+wc/camera[2,2])
        tile=depth[y0:y1+1,x0:x1+1];mask=(wa>=0)&(wb>=0)&(wc>=0)&(z<tile)
        tile[mask]=z[mask]
        if smooth_shade is None:
            image[y0:y1+1,x0:x1+1][mask]=np.clip(color*shade,0,255).astype(np.uint8)
        else:
            lighting=wa[mask]*smooth_shade[0]+wb[mask]*smooth_shade[1]+wc[mask]*smooth_shade[2]
            image[y0:y1+1,x0:x1+1][mask]=np.clip(color[None]*lighting[:,None],0,255).astype(np.uint8)

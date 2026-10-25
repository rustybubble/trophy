"""Export synchronized original images with reconstructed points reprojected.

Shows actual source pixels under the markers; no synthetic footage or reference
ball positions enter this diagnostic. Per-camera frame IDs are burned in.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,numpy as np
from trophy.pipeline import Encoder,verify_video
from trophy.replay.multiview import load_camera,project,BODY_EDGES
from scripts.render_replay import render_frame


def render(config,scene_path,output):
    cfg=json.loads(Path(config).read_text());s=json.loads(Path(scene_path).read_text())
    cameras=[load_camera(v['calibration']) for v in cfg['views']];caps=[cv2.VideoCapture(v['video']) for v in cfg['views']]
    fps=[c.get(cv2.CAP_PROP_FPS) for c in caps];enc=Encoder(output,1920,540,s['fps']);sheets=[]
    selected=[30,75,125,175,225,275]
    try:
        for f in s['frames']:
            panels=[]
            for i,(cap,c) in enumerate(zip(caps,cameras)):
                target=f['time']+s['source_offsets_seconds'][i];idx=min(round(target*fps[i]),int(cap.get(cv2.CAP_PROP_FRAME_COUNT))-1)
                cap.set(cv2.CAP_PROP_POS_FRAMES,idx);ok,im=cap.read()
                if not ok:raise RuntimeError(f'Failed to decode camera {i} frame {idx}')
                for p in f['players']:
                    if not p.get('joints'):continue
                    q=np.array(p['joints']);world=np.c_[q[:,1],-q[:,0],q[:,2]-.76];uv=project(world,c)
                    for a,b in BODY_EDGES:cv2.line(im,tuple(uv[a].astype(int)),tuple(uv[b].astype(int)),(255,160,80) if p['id']==0 else (80,160,255),2,cv2.LINE_AA)
                b=f['ball']
                if b.get('raw_world_position_m') is not None:
                    uv=tuple(np.rint(project(b['raw_world_position_m'],c)[0]).astype(int));cv2.circle(im,uv,12,(0,255,100),2,cv2.LINE_AA);cv2.drawMarker(im,uv,(0,255,100),cv2.MARKER_CROSS,18,1)
                label=f'CAM {i+1} frame {idx} | t={target:.3f}s | ball {b["status"]}'
                cv2.putText(im,label,(20,38),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,0,0),4,cv2.LINE_AA);cv2.putText(im,label,(20,38),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2,cv2.LINE_AA)
                panels.append(cv2.resize(im,(960,540)))
            enc.write(np.hstack(panels))
            if f['frame_index'] in selected:
                small=[cv2.resize(p,(640,360)) for p in panels];solid=cv2.resize(render_frame(s,f['frame_index']), (640,360));sheets.append(np.hstack(small+[solid]))
        enc.close()
    except Exception:
        if not enc.log.closed:enc.abort()
        raise
    finally:
        for c in caps:c.release()
    if sheets:cv2.imwrite(str(Path(output).with_name('contact-sheet.jpg')),np.vstack(sheets))
    report=verify_video(output,len(s['frames']),s['fps']);print(json.dumps(report));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--scene',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();render(a.config,a.scene,a.output)

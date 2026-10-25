"""Render an estimated toss review from the user's actual two-camera footage.

This deliberately uses an explicit demo-estimate mode, not the supported-ruling
gate. Source observations, reviewed release timing, camera fit, synchronization,
and nominal comparisons are retained. It never manufactures a different toss.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import av
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/serve-legality/actual-demo'
SOURCE=ROOT/'configs/actual-toss-demo-session.json'
GEOMETRY=ROOT/'configs/actual-toss-demo-geometry.json'
TRACK_ROIS=[(650,850,1200,1300),(2070,1100,2550,1580)]
DISPLAY_ROIS=[(400,650,2000,1550),(1600,950,3200,1850)]
RELEASE=442/60  # Reviewed first-free frame; neighboring frames retained in report.
APEX=450/60
OFFSET=5/60
BG='#0c1116';PANEL='#15202a';TEXT='#eef4f7';MUTED='#9cacba'
MINT='#9df1cb';GOLD='#ffcf79';RED='#ff9c91';BLUE='#92bfff'
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def font(size,bold=False):return ImageFont.truetype(BOLD if bold else FONT,size)


def prepare(session):
    cache=OUT/'frames';cache.mkdir(parents=True,exist_ok=True)
    identity=[dict(video=v['video'],size=Path(v['video']).stat().st_size,
                   mtime=Path(v['video']).stat().st_mtime_ns) for v in session['views']]
    signature=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    target=OUT/'native-tracks.json'
    if target.exists():
        data=json.loads(target.read_text())
        if data.get('signature')==signature:return data
    result=dict(signature=signature,source_identity=identity,views=[])
    for index,view in enumerate(session['views']):
        rows=[];grays=[];folder=cache/f'camera{index+1}';folder.mkdir(exist_ok=True)
        with av.open(view['video']) as container:
            stream=container.streams.video[0];stream.thread_type='AUTO';stream.codec_context.thread_count=2
            origin=float(stream.start_time*stream.time_base) if stream.start_time is not None else 0.
            container.seek(int((6.8+origin)/stream.time_base),stream=stream,backward=True)
            for frame in container.decode(stream):
                stamp=float(frame.pts*stream.time_base)-origin
                if stamp<6.85:continue
                if stamp>8.25:break
                image=frame.to_ndarray(format='bgr24');h,w=image.shape[:2]
                x0,y0,x1,y1=TRACK_ROIS[index];crop=image[y0:y1,x0:x1]
                hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
                # At the reviewed early oblique frame the small ball is partly
                # occluded by the fingers; a lower saturation threshold recovers
                # its visible pixels. This override is explicitly saved.
                early=index==1 and abs(stamp-7.45)<.002
                mask=cv2.inRange(hsv,np.array([2,130 if early else 145,130 if early else 140]),np.array([30,255,255]))
                count,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
                candidates=[]
                for k in range(1,count):
                    x,y,cw,ch,area=stats[k]
                    if 45<=area<=1800 and .45<cw/ch<2.2 and area/(cw*ch)>.45:
                        candidates.append(dict(x=float(centers[k,0]+x0),y=float(centers[k,1]+y0),area_px=int(area)))
                x0,y0,x1,y1=DISPLAY_ROIS[index]
                filename=folder/f'{round(stamp*60):05d}.jpg'
                cv2.imwrite(str(filename),image[y0:y1,x0:x1],[cv2.IMWRITE_JPEG_QUALITY,93])
                gray=cv2.cvtColor(cv2.resize(image,(960,540)),cv2.COLOR_BGR2GRAY);grays.append(gray)
                rows.append(dict(source_time_seconds=stamp,frame=round(stamp*60),crop=str(filename.relative_to(OUT)),
                    ball=candidates[0] if len(candidates)==1 else None,early_saturation_override=early))
        # Static ceiling/wall features compensate small camera movement relative
        # to the existing 8-second calibration. No player or ball is used as a
        # stabilization reference.
        reference=grays[min(range(len(rows)),key=lambda j:abs(rows[j]['source_time_seconds']-8.))]
        mask=np.zeros_like(reference);mask[:240]=255
        points=cv2.goodFeaturesToTrack(reference,350,.01,7,mask=mask)
        for row,gray in zip(rows,grays):
            moved,status,_=cv2.calcOpticalFlowPyrLK(reference,gray,points,None,winSize=(31,31),maxLevel=4)
            valid=status.ravel().astype(bool)
            H,inliers=cv2.findHomography(moved[valid],points[valid],cv2.RANSAC,1.5)
            if H is None:raise RuntimeError('Static-background registration failed')
            S=np.diag([w/960,h/540,1.]);native=S@H@np.linalg.inv(S)
            row['source_to_reference_homography']=native.tolist()
            row['background_inliers']=int(inliers.sum())
            if row['ball']:
                p=native@np.array([row['ball']['x'],row['ball']['y'],1.])
                row['ball']['reference_xy']=(p[:2]/p[2]).tolist()
        result['views'].append(dict(id=view['id'],rows=rows))
        print(f"Camera {index+1}: {len(rows)} actual timestamped frames; static registration complete",flush=True)
    target.write_text(json.dumps(result,indent=2));return result


def main():
    global OUT, SOURCE, GEOMETRY
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,default=SOURCE,help='JSON with session_id and two local video views')
    parser.add_argument('--geometry',type=Path,default=GEOMETRY,help='JSON with the two fitted cameras')
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args()
    SOURCE=args.session.resolve();GEOMETRY=args.geometry.resolve();OUT=args.output.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    session=json.loads(SOURCE.read_text());data=prepare(session)
    geometry=json.loads(GEOMETRY.read_text());cameras=geometry['cameras'];P=[np.array(c['P']) for c in cameras]
    def observation(index,stamp):
        rows=[r for r in data['views'][index]['rows'] if r['ball'] and 7.35<=r['source_time_seconds']<=7.8]
        times=[r['source_time_seconds'] for r in rows]
        if not times[0]-.001<=stamp<=times[-1]+.001:raise ValueError('No observed ball bracket at requested time')
        return np.array([np.interp(stamp,times,[r['ball']['reference_xy'][k] for r in rows]) for k in range(2)])
    def xyz(stamp):
        uv=[observation(i,stamp+(OFFSET if i else 0))/2 for i in range(2)]
        h=cv2.triangulatePoints(P[0],P[1],uv[0],uv[1]).ravel();point=h[:3]/h[3]
        errors=[]
        for camera,pixel in zip(P,uv):
            q=camera@np.r_[point,1.];errors.append(float(np.linalg.norm(q[:2]/q[2]-pixel)))
        return point,errors
    release,re=xyz(RELEASE);apex,ae=xyz(APEX);delta=apex-release
    height=float(delta[2]);horizontal=float(np.linalg.norm(delta[:2]));angle=math.degrees(math.atan2(horizontal,height))
    verdicts=dict(height='below minimum' if height<.16 else 'meets minimum',
                  angle='exceeds TTR limit' if angle>30 else 'within TTR limit')
    report=dict(mode='demo_estimate_from_actual_footage',synthetic_footage=False,session_id=session['session_id'],
        source_identity=data['source_identity'],source_interval_seconds=[6.9,8.],release_source_a_seconds=RELEASE,
        release_review_interval_source_a_seconds=[7.35,7.383333333333333],apex_source_a_seconds=APEX,
        camera_b_offset_seconds=OFFSET,offset_method='Visual orange-ball apex alignment; nearest 60 FPS frame',
        calibration_source=str(GEOMETRY),calibration_sha256=hashlib.sha256(GEOMETRY.read_bytes()).hexdigest(),
        release_world_m=release.tolist(),apex_world_m=apex.tolist(),height_cm=height*100,angle_degrees=angle,
        reprojection_error_release_px=re,reprojection_error_apex_px=ae,estimated_comparisons=verdicts,
        rule_id='ITTF 2.6.2',height_minimum_cm=16,angle_criterion='ITTF TTR maximum 30 degrees',
        sources=['https://db.ittf.com/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf#page=41',
                 'https://www.ittf.com/2024/12/08/table-tennis-review-system-returns-with-a-successful-trial-at-ittf-mixed-team-world-cup-2024/'],
        limitations=['Demo estimates, not validated officiating measurements.',
                    'The first-free release frame was reviewed manually.',
                    'Camera fit is approximate; background homographies compensate small motion.',
                    'Angle is the 3D release-to-apex chord; no spin or visibility ruling is made.'])
    (OUT/'measurements.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(height_cm=height*100,angle_degrees=angle,comparisons=verdicts,reprojection_px=[re,ae])),flush=True)
    endpoints=[]
    for i,camera in enumerate(cameras):
        p=np.array(camera['P'])
        def proj(x):
            q=p@np.r_[x,1.];return q[:2]/q[2]*2
        r=observation(i,RELEASE+(OFFSET if i else 0));a=observation(i,APEX+(OFFSET if i else 0))
        endpoints.append(dict(release=r,apex=a,reference16=r+proj(release+[0,0,.16])-proj(release)))
    frame_cache={}
    def render(stamp,stage):
        key=(round(stamp*60),stage)
        if key in frame_cache:return frame_cache[key]
        image=Image.new('RGB',(1920,1080),BG);draw=ImageDraw.Draw(image)
        draw.text((48,34),'TROPHY  /  SERVE REVIEW',font=font(29,True),fill=MINT)
        draw.text((1330,38),'ACTUAL TWO-CAMERA FOOTAGE',font=font(21,True),fill=MUTED)
        complete=stamp>=APEX-.001 or stage=='result'
        title=('Estimated toss faults detected' if complete and (height<.16 or angle>30) else
               'Toss measured' if complete else 'Tracking the serving action')
        draw.text((48,86),title,font=font(38,True),fill=TEXT)
        speed='APEX FREEZE' if stage in ('apex','result') else 'SLOW-MOTION REPLAY'
        draw.text((1410,95),speed,font=font(20,True),fill=GOLD)
        for index,(view,roi) in enumerate(zip(data['views'],DISPLAY_ROIS)):
            source_time=stamp+(OFFSET if index else 0)
            row=min(view['rows'],key=lambda r:abs(r['source_time_seconds']-source_time))
            x=48+index*924;y=174;w=900;h=506
            crop=Image.open(OUT/row['crop']).convert('RGB').resize((w,h),Image.Resampling.LANCZOS);image.paste(crop,(x,y))
            draw=ImageDraw.Draw(image)
            draw.text((x,143),f"{'SIDE CAMERA' if index==0 else 'OBLIQUE CAMERA'}   |   source {row['source_time_seconds']:.3f} s",font=font(20,True),fill=MUTED)
            inverse=np.linalg.inv(np.array(row['source_to_reference_homography']))
            def screen(reference):
                q=inverse@np.r_[reference,1.];native=q[:2]/q[2]
                return (float(x+(native[0]-roi[0])*w/(roi[2]-roi[0])),float(y+(native[1]-roi[1])*h/(roi[3]-roi[1])))
            trail=[r for r in view['rows'] if r['ball'] and RELEASE+(OFFSET if index else 0)-.001<=r['source_time_seconds']<=min(source_time,APEX+(OFFSET if index else 0))+.001]
            if len(trail)>1:draw.line([screen(r['ball']['reference_xy']) for r in trail],fill=GOLD,width=4)
            if row['ball']:
                px,py=screen(row['ball']['reference_xy']);draw.ellipse((px-10,py-10,px+10,py+10),outline=GOLD,width=3)
            if stamp>=RELEASE-.001:
                r=screen(endpoints[index]['release']);ref=screen(endpoints[index]['reference16'])
                draw.line([r,ref],fill=BLUE,width=3);draw.ellipse((r[0]-5,r[1]-5,r[0]+5,r[1]+5),fill=MINT)
                draw.line([(ref[0]-14,ref[1]),(ref[0]+14,ref[1])],fill=BLUE,width=4)
                draw.text((ref[0]+18,ref[1]-16),'16 cm minimum',font=font(20,True),fill=BLUE,stroke_width=2,stroke_fill='#0c1116')
                draw.text((r[0]+14,r[1]+10),'Release',font=font(20,True),fill=MINT,stroke_width=2,stroke_fill='#0c1116')
                if complete:
                    a=screen(endpoints[index]['apex']);draw.line([r,a],fill=RED,width=4)
                    draw.ellipse((a[0]-7,a[1]-7,a[0]+7,a[1]+7),outline=RED,width=3)
                    draw.text((a[0]+15,a[1]-28),'Apex',font=font(20,True),fill=RED,stroke_width=2,stroke_fill='#0c1116')
            draw.text((x,696),'Observed ball path' if not complete else 'Release → apex · measurements use both camera views',font=font(20),fill=MUTED)
        for x in [48,604]:draw.rounded_rectangle((x,746,x+526,990),18,fill=PANEL,outline='#2a3a46',width=2)
        draw.text((72,765),'TOSS HEIGHT',font=font(22,True),fill=MUTED)
        draw.text((628,765),'TOSS ANGLE FROM VERTICAL',font=font(22,True),fill=MUTED)
        if complete:
            draw.text((72,802),f'{height*100:.1f} cm',font=font(68,True),fill=RED if height<.16 else MINT)
            draw.text((628,802),f'{angle:.1f}°',font=font(68,True),fill=RED if angle>30 else MINT)
            draw.text((72,889),'BELOW MINIMUM' if height<.16 else 'MEETS MINIMUM',font=font(23,True),fill=RED if height<.16 else MINT)
            draw.text((628,889),'TTR LIMIT EXCEEDED' if angle>30 else 'WITHIN TTR LIMIT',font=font(23,True),fill=RED if angle>30 else MINT)
        else:
            draw.text((72,802),'Measuring…',font=font(42,True),fill=TEXT)
            draw.text((628,802),'Tracking…',font=font(42,True),fill=TEXT)
            draw.text((72,889),'Release-to-apex vertical rise',font=font(22),fill=MUTED)
            draw.text((628,889),'3D release-to-apex direction',font=font(22),fill=MUTED)
        draw.text((72,941),'ITTF 2.6.2  ·  minimum 16 cm',font=font(22),fill=TEXT)
        draw.text((628,941),'ITTF TTR criterion  ·  maximum 30°',font=font(22),fill=TEXT)
        draw.rounded_rectangle((1160,746,1872,990),18,fill=PANEL,outline='#2a3a46',width=2)
        draw.text((1190,764),'MEASUREMENT PLANE',font=font(22,True),fill=MUTED)
        r=(1240,958);scale=825;top=(r[0],r[1]-.16*scale)
        draw.line([r,(r[0],810)],fill=BLUE,width=3)
        draw.line([(r[0]-13,top[1]),(r[0]+13,top[1])],fill=BLUE,width=4)
        a=(r[0]+horizontal*scale,r[1]-height*scale)
        lim=(r[0]+math.tan(math.radians(30))*140,r[1]-140)
        draw.line([r,lim],fill='#51606d',width=2)
        if complete:
            draw.line([r,a],fill=RED,width=4);draw.ellipse((a[0]-6,a[1]-6,a[0]+6,a[1]+6),fill=RED)
            draw.arc((r[0]-43,r[1]-43,r[0]+43,r[1]+43),270,270+angle,fill=GOLD,width=3)
        draw.ellipse((r[0]-5,r[1]-5,r[0]+5,r[1]+5),fill=MINT)
        draw.text((1395,812),'Blue: 16 cm vertical reference',font=font(20),fill=BLUE)
        draw.text((1395,850),'Gray: 30° TTR direction limit',font=font(20),fill=MUTED)
        draw.text((1395,888),'Red: estimated actual toss',font=font(20),fill=RED)
        draw.text((1395,928),'3D angle, not the screen angle',font=font(19),fill=MUTED)
        draw.text((48,1024),'DEMO ESTIMATES  ·  Reviewed release frame  ·  Table-based camera fit  ·  Visual sync +83 ms',font=font(21),fill=MUTED)
        frame=np.asarray(image);frame_cache[key]=frame;return frame
    timeline=[]
    for seconds,start,end,stage in [(3.,6.9,7.3,'track'),(3.,7.3,7.5,'track'),(5.,7.5,7.5,'apex'),(4.,7.5,8.,'flight'),(5.,7.5,7.5,'result')]:
        timeline.extend((float(t),stage) for t in np.linspace(start,end,round(seconds*30),endpoint=False))
    video=OUT/'toss-legality-demo.mp4'
    with av.open(str(video),'w',options={'movflags':'+faststart'}) as container:
        stream=container.add_stream('libx264',rate=30);stream.width=1920;stream.height=1080;stream.pix_fmt='yuv420p';stream.options={'crf':'19','preset':'fast'}
        for i,(stamp,stage) in enumerate(timeline):
            frame=av.VideoFrame.from_ndarray(render(stamp,stage),format='rgb24')
            for packet in stream.encode(frame):container.mux(packet)
            if i%150==0:print(f'Rendered {i}/{len(timeline)} demo frames',flush=True)
        for packet in stream.encode():container.mux(packet)
    Image.fromarray(render(APEX,'result')).save(OUT/'demo-poster.jpg',quality=95)
    report.update(output=str(video),output_duration_seconds=len(timeline)/30,output_frames=len(timeline),output_fps=30)
    (OUT/'measurements.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Trophy · Actual footage demo</title><style>body{background:#0c1116;color:#eef4f7;font:16px system-ui;margin:30px auto;max-width:1400px;padding:0 24px}video{width:100%;border-radius:12px}a{color:#9df1cb}p{color:#9cacba}</style><h1>Serve legality · actual footage demo</h1><video controls playsinline preload="metadata" poster="demo-poster.jpg" src="toss-legality-demo.mp4"></video><p>Real source footage with estimated 3D toss height, angle, and rule comparisons. Release was reviewed; camera geometry is approximate.</p><a href="toss-legality-demo.mp4" download>Download MP4</a> · <a href="measurements.json">Measurements and provenance</a>''')
    # Attach the finished demo to the existing review without replacing its
    # candidates or changing the supported-ruling quality gates.
    if 'events' not in session:
        print(json.dumps(report,indent=2),flush=True)
        return
    shutil.copy2(video,SOURCE.parent/'toss-legality-demo.mp4')
    shutil.copy2(OUT/'demo-poster.jpg',SOURCE.parent/'demo-poster.jpg')
    shutil.copy2(OUT/'index.html',SOURCE.parent/'actual-demo.html')
    shutil.copy2(OUT/'measurements.json',SOURCE.parent/'measurements.json')
    session['demo_video']='toss-legality-demo.mp4'
    SOURCE.write_text(json.dumps(session,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()

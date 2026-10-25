"""Export a complete ball-only replay, overhead view and source comparison."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('PYOPENGL_PLATFORM', 'darwin' if sys.platform == 'darwin' else 'egl')
import cv2
import numpy as np
import pyrender
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.render_hmr2_replay import build_static, camera_pose, mesh
from trophy.pipeline import Encoder, verify_video
from trophy.replay.multiview import project


def label(image, text, xy, scale=.65, color=(225, 235, 245), thickness=1):
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, (15, 22, 30), thickness+3, cv2.LINE_AA)
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def camera_panel(cap, source_frame, row, camera, source_rows, view, output_size=(960, 540)):
    # Source time and row lookup are explicit even when the 30-fps alignment
    # selects the previous/next source image.
    requested = max(0, min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT))-1, source_frame))
    current = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    if current != requested:
        cap.set(cv2.CAP_PROP_POS_FRAMES, requested)
    ok, original = cap.read()
    if not ok:
        raise ValueError(f'Cannot decode camera {view}, frame {requested}')
    height, width = original.shape[:2]
    image = cv2.resize(original, output_size, interpolation=cv2.INTER_AREA)
    scale = np.array(output_size)/[width, height]
    detection = source_rows[requested]
    if detection['detected']:
        pixel = tuple(np.rint(np.array([detection['x'], detection['y']])*scale).astype(int))
        cv2.circle(image, pixel, 5, (100, 235, 140), 1, cv2.LINE_AA)
    point = row['ball']['world_position_m']
    if point is not None:
        pixel = tuple(np.rint(project(point, camera)[0]*scale).astype(int))
        if -20 <= pixel[0] < output_size[0]+20 and -20 <= pixel[1] < output_size[1]+20:
            cv2.circle(image, pixel, 7, (255, 225, 70), 1, cv2.LINE_AA)
    label(image, f'CAMERA {view}  /  {requested/30:.2f}s', (20, 32), .6)
    label(image, 'Green: detector   Cyan: 3D projection', (20, output_size[1]-18), .45)
    return image


def render(directory, width=1920, height=1080):
    started = time.perf_counter()
    out = Path(directory).resolve()
    scene_data = json.loads((out/'scene.json').read_text())
    frames, fps = scene_data['frames'], scene_data['fps']
    cameras = [{k: np.array(v) for k, v in c.items()} for c in scene_data['cameras']]
    source_rows = [json.loads((Path(p).parent/f'ball-camera{i}/detections.json').read_text())
                   for i, p in enumerate(scene_data['sources'], 1)]
    scene = build_static()
    camera = scene.add(pyrender.PerspectiveCamera(yfov=np.radians(37), znear=.05),
                       pose=camera_pose(np.array([4.5, -4.8, 3.7]), [0, 0, .9]))
    if sys.platform == 'darwin':
        os.environ.pop('PYOPENGL_PLATFORM', None)
    renderer = pyrender.OffscreenRenderer(width, height)
    videos = {
        'ball-only-3d.mp4': Encoder(out/'ball-only-3d.mp4', width, height, fps),
        'ball-only-overhead.mp4': Encoder(out/'ball-only-overhead.mp4', width, height, fps),
        'source-comparison.mp4': Encoder(out/'source-comparison.mp4', 1920, 1080, fps),
    }
    caps = [cv2.VideoCapture(p) for p in scene_data['sources']]
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=.02)
    ball_mesh = mesh(sphere.vertices, sphere.faces, [1., .60, .12, 1.])
    dynamic = []
    sheets = []
    selected = [0, 90, 150, 240, 330, len(frames)-1]
    try:
        for i, frame in enumerate(frames):
            for node in dynamic:
                scene.remove_node(node)
            dynamic = []
            ball = frame['ball']
            if ball['position'] is not None:
                pose = np.eye(4)
                pose[:3, 3] = ball['position']
                dynamic.append(scene.add(ball_mesh, pose=pose))
            for j in range(max(0, i-9), i):
                a, b = frames[j]['ball']['position'], frames[j+1]['ball']['position']
                if a is None or b is None or np.linalg.norm(np.array(a)-b) < 1e-6:
                    continue
                fade = (j-max(0, i-9)+1)/10
                line = trimesh.creation.cylinder(radius=.004, segment=np.array([a, b]), sections=6)
                color = [.12+.17*fade, .34+.4*fade, .35+.38*fade, 1.]
                dynamic.append(scene.add(mesh(line.vertices, line.faces, color)))

            # A slow, bounded orbit keeps table ends on screen across the clip.
            phase = .72 + .12*np.sin(2*np.pi*i/max(1, len(frames)-1))
            eye = np.array([4.65*np.sin(phase), -4.65*np.cos(phase), 2.8])
            scene.set_pose(camera, camera_pose(eye, [0, 0, .93]))
            color, _ = renderer.render(scene)
            main = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
            zoom = np.clip((frame['time']-3.5), 0, 1)
            zoom = zoom*zoom*(3-2*zoom)
            overhead_height = 4.05 + 1.35*(1-zoom)
            scene.set_pose(camera, camera_pose(np.array([0., -.001, overhead_height]), [0, 0, .76]))
            color, _ = renderer.render(scene)
            overhead = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
            for image, name in [(main, '3D BALL REPLAY'), (overhead, 'OVERHEAD')]:
                label(image, f'TROPHY  /  {name}', (48, 56), .85)
                label(image, f'{frame["time"]:05.2f} / {scene_data["duration"]:.2f} s', (width-310, 56), .65)
                label(image, 'Estimated reconstruction / smoothed trajectory includes gap estimates',
                      (48, height-38), .55, (170, 190, 205))
                if ball['position'] is None:
                    label(image, 'SETUP / BALL POSITION UNAVAILABLE', (48, height-77), .58, (130, 170, 205))
                elif not ball['measured_3d']:
                    label(image, 'BALL POSITION ESTIMATED', (48, height-77), .5, (110, 190, 245))
            videos['ball-only-3d.mp4'].write(main)
            videos['ball-only-overhead.mp4'].write(overhead)
            panels = []
            for view, (cap, c, source) in enumerate(zip(caps, cameras, source_rows), 1):
                source_time = frame['time']+scene_data['source_offsets_seconds'][view-1]
                source_frame = round(source_time*fps)
                panels.append(camera_panel(cap, source_frame, frame, c, source, view))
            comparison = np.vstack([np.hstack(panels),
                                    np.hstack([cv2.resize(main, (960, 540)), cv2.resize(overhead, (960, 540))])])
            videos['source-comparison.mp4'].write(comparison)
            if i in selected:
                cv2.imwrite(str(out/f'frame-{i:03d}.jpg'), comparison)
                sheets.append(cv2.resize(comparison, (1280, 720)))
            if i == 240:
                cv2.imwrite(str(out/'poster.jpg'), main)
            if i % 30 == 0:
                print(f'Rendered {i+1}/{len(frames)} / {time.perf_counter()-started:.1f}s elapsed', flush=True)
        for video in videos.values():
            video.close()
    except Exception:
        for video in videos.values():
            if not video.log.closed:
                video.abort()
        raise
    finally:
        renderer.delete()
        for cap in caps:
            cap.release()
    cv2.imwrite(str(out/'contact-sheet.jpg'), np.vstack(sheets))
    report = {name: verify_video(out/name, len(frames), fps) for name in videos}
    report['render_seconds'] = time.perf_counter()-started
    report['player_meshes_loaded'] = False
    (out/'render-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    render(args.directory)

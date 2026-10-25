"""Render fitted SMPL bodies and measured ball points, plus source overlays."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

os.environ.setdefault('PYOPENGL_PLATFORM', 'darwin' if sys.platform == 'darwin' else 'egl')
import cv2
import numpy as np
import pyrender
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trophy.pipeline import Encoder, verify_video
from trophy.replay.multiview import viewer_coordinates

ROOT = Path(__file__).resolve().parents[1]
COLORS = [[.31, .76, .65, 1], [.47, .55, .94, 1]]


def camera_pose(eye, target):
    forward = np.array(target) - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0., 0, 1])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    pose = np.eye(4)
    pose[:3, :3] = np.c_[right, up, -forward]
    pose[:3, 3] = eye
    return pose


def mesh(vertices, faces, color):
    material = pyrender.MetallicRoughnessMaterial(baseColorFactor=color,
                                                metallicFactor=.02, roughnessFactor=.75,
                                                doubleSided=True)
    return pyrender.Mesh.from_trimesh(trimesh.Trimesh(vertices, faces, process=False),
                                      material=material, smooth=True)


def box(scene, center, extent, color):
    shape = trimesh.creation.box(extents=extent)
    shape.apply_translation(center)
    scene.add(mesh(shape.vertices, shape.faces, color))


def build_static():
    scene = pyrender.Scene(bg_color=[.05, .085, .13, 1], ambient_light=[.5]*3)
    box(scene, [0, 0, -.02], [14, 12, .02], [.08, .12, .17, 1])
    box(scene, [0, 0, .7325], [2.74, 1.525, .055], [.16, .34, .46, 1])
    for x in [-1.05, 1.05]:
        for y in [-.55, .55]:
            box(scene, [x, y, .36], [.045, .045, .72], [.4, .46, .5, 1])
    for y in [-.756, .756]:
        box(scene, [0, y, .762], [2.74, .012, .003], [.9, .95, 1, 1])
    for x in [-1.364, 1.364]:
        box(scene, [x, 0, .762], [.012, 1.525, .003], [.9, .95, 1, 1])
    box(scene, [0, 0, .763], [2.74, .008, .003], [.8, .9, .95, 1])
    for y in np.linspace(-.9, .9, 37):
        box(scene, [0, y, .83625], [.004, .0025, .1525], [.55, .65, .7, 1])
    for z in np.linspace(.76, .9125, 5):
        box(scene, [0, 0, z], [.004, 1.8, .0025], [.6, .7, .75, 1])
    light_pose = camera_pose(np.array([3., -4, 7]), [0, 0, 0])
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=2.5), pose=light_pose)
    return scene


def render(directory):
    out = Path(directory)
    data = np.load(out / 'fitted-bodies.npz')
    metadata = json.loads((out / 'scene.json').read_text())
    geometry = np.load(ROOT / 'artifacts/user-two-camera/hmr2/geometry.npz')
    vertices = viewer_coordinates(data['vertices'])
    faces = data['faces']
    scene = build_static()
    render_camera = scene.add(pyrender.PerspectiveCamera(yfov=np.radians(46)),
                               pose=camera_pose(np.array([4.8, -5.5, 3.2]), [0, 0, .9]))
    overlay = pyrender.Scene(bg_color=[0, 0, 0, 0], ambient_light=[.8]*3)
    overlay.add(pyrender.DirectionalLight(color=np.ones(3), intensity=1.8),
                pose=camera_pose(np.array([3., -4, 7]), [0, 0, 0]))
    overlay_camera = None
    # PyRender's native macOS backend uses Pyglet when the variable is absent;
    # PyOpenGL has already selected the Darwin platform above.
    if sys.platform == 'darwin':
        os.environ.pop('PYOPENGL_PLATFORM', None)
    renderer = pyrender.OffscreenRenderer(1280, 720)
    source_renderer = pyrender.OffscreenRenderer(1920, 1080)
    video = Encoder(out / 'orbit.mp4', 1280, 720, 30)
    comparison = Encoder(out / 'comparison.mp4', 1920, 360, 30)
    caps = [cv2.VideoCapture(str(ROOT / f'artifacts/user-two-camera/camera{i}-8s-14s.mp4'))
            for i in [1, 2]]
    changing, changing_overlay, sheets = [], [], []
    sphere = trimesh.creation.icosphere(subdivisions=2, radius=.02)
    transform_axes = np.array([[0., -1, 0], [1, 0, 0], [0, 0, 1]])
    try:
        for frame, timestamp in enumerate(data['times']):
            for n in changing:
                scene.remove_node(n)
            for n in changing_overlay:
                overlay.remove_node(n)
            changing, changing_overlay = [], []
            for player in range(2):
                changing.append(scene.add(mesh(vertices[frame, player], faces, COLORS[player])))
                changing_overlay.append(overlay.add(mesh(vertices[frame, player], faces, COLORS[player])))
            ball = metadata['frames'][frame]['ball']['position']
            if ball is not None:
                q = sphere.vertices + np.array(ball)
                changing.append(scene.add(mesh(q, sphere.faces, [1., .6, .2, 1.])))
                changing_overlay.append(overlay.add(mesh(q, sphere.faces, [1., .6, .2, 1.])))
            # A gentle changing viewpoint makes recovered depth inspectable.
            phase = .25 * np.sin(frame / max(1, len(vertices)-1) * np.pi * 2)
            eye = np.array([6.7*np.sin(.72+phase), -6.7*np.cos(.72+phase), 3.2])
            scene.set_pose(render_camera, camera_pose(eye, [0, 0, .9]))
            color, _ = renderer.render(scene)
            bgr = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
            cv2.putText(bgr, 'TROPHY / 4D HUMANS + TWO-VIEW BALL', (28, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (225, 235, 245), 1, cv2.LINE_AA)
            cv2.putText(bgr, f'Source {timestamp+8:.2f}s | Estimated reconstruction; hidden joints inferred',
                        (28, 690), cv2.FONT_HERSHEY_SIMPLEX, .45, (175, 190, 205), 1, cv2.LINE_AA)
            video.write(bgr)
            panels = []
            for view in range(2):
                if overlay_camera is not None:
                    overlay.remove_node(overlay_camera)
                K, R, center = (geometry[k][view] for k in ['K', 'R', 'center'])
                pose = np.eye(4)
                pose[:3, :3] = transform_axes @ R.T @ np.diag([1., -1, -1])
                pose[:3, 3] = viewer_coordinates(center)
                overlay_camera = overlay.add(pyrender.IntrinsicsCamera(
                    fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2], znear=.05, zfar=100), pose=pose)
                overlay.main_camera_node = overlay_camera
                rgba, _ = source_renderer.render(overlay, flags=pyrender.RenderFlags.RGBA)
                source_index = min(179, round((timestamp + metadata['source_offsets_seconds'][view]) * 60))
                rgba = cv2.warpPerspective(rgba, geometry['homographies'][view, source_index], (1920, 1080))
                cap = caps[view]
                cap.set(cv2.CAP_PROP_POS_FRAMES, source_index)
                ok, original = cap.read()
                if not ok:
                    raise ValueError('Source overlay frame unavailable')
                alpha = rgba[:, :, 3:4].astype(float) / 255 * .55
                blended = np.clip(original * (1-alpha) + rgba[:, :, :3][:, :, ::-1] * alpha, 0, 255).astype(np.uint8)
                label = f'CAM {view+1} / mesh overlay / source frame {source_index}'
                cv2.putText(blended, label, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(blended, label, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, .7, (240, 245, 250), 1, cv2.LINE_AA)
                panels.append(cv2.resize(blended, (640, 360)))
            combined = np.hstack([*panels, cv2.resize(bgr, (640, 360))])
            comparison.write(combined)
            if frame in [0, len(vertices)//3, 2*len(vertices)//3, len(vertices)-1]:
                sheets.append(combined)
                cv2.imwrite(str(out / f'frame-{frame:03d}.jpg'), bgr)
            if frame % 15 == 0:
                print(f'Rendered {frame+1}/{len(vertices)} reconstructed frames', flush=True)
        video.close()
        comparison.close()
    except Exception:
        if not video.log.closed:
            video.abort()
        if not comparison.log.closed:
            comparison.abort()
        raise
    finally:
        for cap in caps:
            cap.release()
        renderer.delete()
        source_renderer.delete()
    cv2.imwrite(str(out / 'contact-sheet.jpg'), np.vstack(sheets))
    reports = [verify_video(out / name, len(vertices), 30)
               for name in ['orbit.mp4', 'comparison.mp4']]
    (out / 'render-report.json').write_text(json.dumps(reports, indent=2))
    for name in ['three.module.js', 'three.core.js', 'OrbitControls.js', 'THREE-LICENSE.txt']:
        shutil.copy2(ROOT / 'web/replay' / name, out / name)
    for path in (ROOT / 'web/hmr2').iterdir():
        shutil.copy2(path, out / path.name)
    for view in [1, 2]:
        shutil.copy2(ROOT / f'artifacts/user-two-camera/camera{view}-8s-14s.mp4', out / f'source{view}.mp4')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', default='artifacts/user-two-camera/reconstruction')
    render(p.parse_args().directory)

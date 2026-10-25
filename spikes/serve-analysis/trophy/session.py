"""Combine the existing offline models into an isolated two-camera session.

All clocks use t_camera2 = t_camera1 + offset. Audio estimates a coarse
offset on the original recordings; visual refinement is on normalized clips.
"""
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

import cv2
import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TABLE_CORNERS = np.array([[-.7625, 1.37, 0], [-.7625, -1.37, 0],
                          [.7625, -1.37, 0], [.7625, 1.37, 0]], float)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False))


def video_info(path):
    cap = cv2.VideoCapture(str(path))
    try:
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        ok, frame = cap.read()
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not ok or not math.isfinite(fps) or fps <= 0 or count < 3:
            raise ValueError(f'Cannot read a usable video: {path}')
        return dict(width=frame.shape[1], height=frame.shape[0], fps=fps,
                    frames=count, duration=count / fps)
    finally:
        cap.release()


def validate_view(view, info):
    points = np.asarray(view.get('table_corners_px'), float)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError('Mark four table corners in each view, using matching A, B, C, D labels')
    w, h = info['width'], info['height']
    if np.any(points < 0) or np.any(points >= [w, h]):
        raise ValueError('Table corners must lie inside the displayed source frame')
    polygon = points.astype(np.float32)
    if not cv2.isContourConvex(polygon) or abs(cv2.contourArea(polygon)) < 100:
        raise ValueError('Table corners must form a convex, non-crossing quadrilateral in A–B–C–D order')
    rois = np.asarray(view.get('player_rois_px'), float)
    if rois.shape != (2, 4) or not np.isfinite(rois).all():
        raise ValueError('Specify two player regions per camera, in the same player order')
    if (np.any(rois < 0) or np.any(rois[:, [0, 2]] > w) or
            np.any(rois[:, [1, 3]] > h) or np.any(rois[:, 2:] - rois[:, :2] < 16)):
        raise ValueError('Player regions must be at least 16 pixels wide/high and fit inside the frame')
    focal = float(view.get('focal_px', 0))
    if not math.isfinite(focal) or focal < 0:
        raise ValueError('Focal length must be zero (estimate) or a positive pixel value')


def calibrate_camera(view, info):
    """Planar table calibration; centered principal point and zero distortion."""
    validate_view(view, info)
    pixels = np.asarray(view['table_corners_px'], float)
    cx, cy = info['width'] / 2, info['height'] / 2
    focal = float(view.get('focal_px', 0))
    if not focal:
        H, _ = cv2.findHomography(TABLE_CORNERS[:, :2], pixels)
        a, b = H[:, 0], H[:, 1]
        numerator = (a[0]-cx*a[2])*(b[0]-cx*b[2]) + (a[1]-cy*a[2])*(b[1]-cy*b[2])
        f2 = -numerator / (a[2]*b[2]) if abs(a[2]*b[2]) > 1e-12 else -1
        if f2 <= 0 or not math.isfinite(f2):
            raise ValueError('Cannot estimate focal length from these corners. Refine the marks or enter calibrated focal length in pixels')
        focal = math.sqrt(f2)
        if not .2*max(info['width'], info['height']) < focal < 10*max(info['width'], info['height']):
            raise ValueError('Estimated focal length is implausible. Refine the table corners or supply focal length')
    K = np.array([[focal, 0, cx], [0, focal, cy], [0, 0, 1.]])
    ok, rv, tv = cv2.solvePnP(TABLE_CORNERS, pixels, K, None, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError('Table calibration failed')
    R = cv2.Rodrigues(rv)[0]
    t = tv.ravel()
    center = -R.T @ t
    if center[2] <= 0 or np.any((TABLE_CORNERS @ R.T + t)[:, 2] <= 0):
        raise ValueError('Calibration places the camera below the table. Check matching physical corner labels in both views')
    from trophy.replay.multiview import project
    camera = dict(K=K, R=R, t=t, P=K @ np.c_[R, t], center=center)
    error = float(np.sqrt(np.mean((project(TABLE_CORNERS, camera) - pixels)**2)))
    automatic = view.get('calibration_mode') == 'automatic_demo'
    if error > (max(8, .006*info['width']) if automatic else 8):
        raise ValueError(f'Table calibration error is {error:.1f}px; refine the four corner marks')
    return camera, dict(table_corner_rmse_px=error, focal_px=focal,
                        method='Automatically segmented demo table; approximate pinhole' if automatic else 'Four matching table corners; centered pinhole; no lens distortion')


def preflight():
    required = ['.venv/bin/python', '.venv-pose/bin/python', '.venv-hmr2/bin/python',
                '.venv-serves/bin/python', 'weights/pose_landmarker_full.task',
                'weights/blurball_best', 'weights/serves/table-tennis-final.pt',
                'weights/hmr2-assets/model_config.yaml',
                'weights/hmr2-assets/logs/train/multiruns/hmr2/0/checkpoints/epoch=35-step=1000000.ckpt']
    missing = [p for p in required if not (ROOT / p).is_file()]
    if missing:
        raise ValueError('Missing local model assets/environments: ' + ', '.join(missing) + '. See README.md, HMR2_REPLAY.md and SERVES.md for setup')


def run_stage(command, log_path, progress, label):
    progress(label, '')
    with Path(log_path).open('w') as log:
        process = subprocess.Popen([str(c) for c in command], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            tail = []
            for line in process.stdout:
                log.write(line)
                log.flush()
                tail = (tail + [line.rstrip()])[-12:]
                progress(label, '\n'.join(tail))
            if process.wait():
                raise RuntimeError(f'{label} failed. See {log_path}\n' + '\n'.join(tail))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()


def shared_segment(infos, start, duration, offset, fps=30):
    if not np.isfinite([start, duration, offset]).all() or start < 0 or duration <= 0:
        raise ValueError('Start, duration and offset must be finite; start >= 0 and duration > 0')
    start_a = max(start, -offset)
    starts = [start_a, start_a + offset]
    length = min(duration, *(v['duration']-s for v, s in zip(infos, starts)))
    count = math.floor(length*fps + 1e-7)
    if count < 45:
        raise ValueError('Need at least 1.5 seconds of overlapping footage for visual synchronization')
    return starts, count


def serve_config(views, videos, infos, offset, session_id):
    result = dict(session_id=session_id, title='Two-camera rally · serve review',
                  players={'p0': 'Player 1', 'p1': 'Player 2'},
                  synchronization_status='shared_visual_offset_with_3d_replay', views=[])
    for index, (view, video, info) in enumerate(zip(views, videos, infos)):
        rois = np.asarray(view['player_rois_px'], float)
        order = np.argsort(rois[:, [0, 2]].mean(axis=1))
        result['views'].append(dict(id=f'Camera {index+1}', video=str(video),
            source_offset_seconds=offset if index else 0,
            player_map={side: f'p{pid}' for side, pid in zip(['left', 'right'], order)},
            player_regions_norm={side: (rois[pid]/[info['width'], info['height'], info['width'], info['height']]).tolist()
                                 for side, pid in zip(['left', 'right'], order)}))
    return result


def package_replay(out, videos, infos, starts, sync):
    replay = out / 'replay'
    scene = json.loads((replay / 'scene.json').read_text())
    serves = json.loads((out / 'serves/serves.json').read_text())
    scene.update(serve_events=[e for e in serves['events'] if scene.get('start_time', 0) <= e['time_seconds'] <= scene['duration']],
                 serve_review_url='review/', synchronization=sync, source_start_seconds=starts,
                 source_sizes=[[i['width'], i['height']] for i in infos],
                 download_videos=False)
    write_json(replay / 'scene.json', scene)
    for name in ['three.module.js', 'three.core.js', 'OrbitControls.js', 'THREE-LICENSE.txt']:
        shutil.copy2(ROOT / 'web/replay' / name, replay / name)
    for path in (ROOT / 'web/hmr2').iterdir():
        if path.is_file():
            shutil.copy2(path, replay / path.name)
    for index, video in enumerate(videos, 1):
        shutil.copy2(video, replay / f'source{index}.mp4')
        shutil.copy2(out / f'ball-camera{index}/detections.json', replay / f'detections{index}.json')
        shutil.copy2(out / f'ball-camera{index}/annotated.mp4', replay / f'ball-camera{index}.mp4')
    review = replay / 'review'
    shutil.copytree(out / 'serves', review)
    # The same normalized clips and residual offset drive both viewers.
    # Relative URLs keep downloaded/static replay bundles fully portable.
    for index, view in enumerate(serves['views']):
        view['review_url'] = f'../source{index+1}.mp4'
    write_json(review / 'serves.json', serves)
    geometry_path = out / 'hmr2/geometry.json'
    if geometry_path.is_file():
        from trophy.serves.legality import calibration_from_reconstruction
        toss_calibration = calibration_from_reconstruction(serves, json.loads(geometry_path.read_text()))
        write_json(review / 'toss-calibration.json', toss_calibration)
    with (replay / 'ball-3d.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['frame_index', 'time_seconds', 'x_m', 'y_m', 'z_m', 'status'])
        for frame in scene['frames']:
            writer.writerow([frame['frame_index'], frame['time'], *(frame['ball']['position'] or ['', '', '']), frame['ball']['status']])
    return scene


def analyze_two_camera(config, output, progress=None):
    """Run existing model CLIs in their own pinned environments; never overwrite."""
    from trophy.replay.multiview import pose_array, reconstruct_ball, synchronize_ball, synchronize_poses
    from scripts.probe_audio_sync import audio_envelope, align_audio
    progress = progress or (lambda stage, detail: None)
    cfg = json.loads(Path(config).read_text()) if isinstance(config, (str, Path)) else config
    views = cfg.get('views', [])
    if len(views) != 2:
        raise ValueError('Upload exactly two camera angles of the same rally')
    if cfg.get('device', 'auto') not in ['auto', 'cpu', 'mps']:
        raise ValueError('Device must be auto, cpu or mps')
    preflight()
    out = Path(output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Choose a new or empty session output directory')
    originals = [Path(v['video']).expanduser().resolve() for v in views]
    infos = [video_info(v) for v in originals]
    calibration = [calibrate_camera(v, i) for v, i in zip(views, infos)]
    cameras = [c[0] for c in calibration]
    started = time.perf_counter()
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / 'session-config.json', cfg)
    sync = {}
    try:
        if cfg.get('sync_mode', 'audio') == 'audio':
            progress('Synchronizing source audio', '')
            (a, sa), (b, sb) = [audio_envelope(v, 120) for v in originals]
            coarse, score = align_audio(a, b, max_lag_seconds=30)
            coarse += sb - sa
            sync.update(audio_correlation=score, method='audio initialization + measured-ball visual refinement')
        elif cfg['sync_mode'] == 'manual':
            coarse = float(cfg.get('offset_seconds', 0))
            sync['method'] = 'user coarse offset + measured-ball visual refinement'
        else:
            raise ValueError('Synchronization mode must be audio or manual')
        starts, count = shared_segment(infos, float(cfg.get('start_seconds', 0)), float(cfg.get('duration_seconds', 6)), coarse)
        sync.update(coarse_original_offset_seconds=coarse, source_start_seconds=starts)
        videos = [out / f'camera{i+1}.mp4' for i in range(2)]
        hmr = out / 'hmr2'
        hmr.mkdir()
        for index, (video, source, start, view) in enumerate(zip(videos, originals, starts, views), 1):
            run_stage([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                       '-ss', start, '-i', source, '-an', '-vf', 'fps=30,pad=ceil(iw/2)*2:ceil(ih/2)*2',
                       '-frames:v', count, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', 18,
                       '-pix_fmt', 'yuv420p', '-movflags', '+faststart', video],
                      out / f'prepare-camera{index}.log', progress, f'Preparing camera {index}')
            if video_info(video)['frames'] != count:
                raise ValueError('A source ended before the requested shared segment')
            run_stage([ROOT / '.venv/bin/python', '-m', 'trophy', video, '--output', out / f'ball-camera{index}',
                       '--device', cfg.get('device', 'auto'), '--max-frames', count,
                       '--threshold', cfg.get('threshold', .7), '--photometric', cfg.get('photometric', 'rgb')],
                      out / f'ball-camera{index}.log', progress, f'Detecting ball · camera {index}')
            pose_config = hmr / f'pose-config{index}.json'
            write_json(pose_config, {'player_rois_px': np.asarray(view['player_rois_px'], int).tolist()})
            run_stage([ROOT / '.venv-pose/bin/python', ROOT / 'scripts/extract_poses.py', video,
                       '--output', hmr / f'poses-camera{index}.json', '--config', pose_config, '--max-frames', count],
                      out / f'pose-camera{index}.log', progress, f'Tracking players · camera {index}')
        rows = [json.loads((out / f'ball-camera{i}/detections.json').read_text()) for i in [1, 2]]
        poses = [pose_array(hmr / f'poses-camera{i}.json') for i in [1, 2]]
        for detections, (ts, _, _) in zip(rows, poses):
            if len(ts) != count or len(detections) != count or not np.allclose(ts, [r['timestamp_seconds'] for r in detections], atol=.002):
                raise ValueError('Pose/ball timestamps differ; refusing misaligned reconstruction')
        progress('Refining camera synchronization and triangulating ball', '')
        initial, pose_sync = synchronize_poses(poses[0][0], poses[0][1], poses[1][0], poses[1][1], cameras)
        # A failed visual fit is explicit; do not silently accept an audio-only 3D clock.
        offset, ball_sync = synchronize_ball(*rows, cameras, initial=initial)
        if ball_sync['cost_px'] >= 15:
            raise ValueError('Cross-camera ball evidence is insufficient for visual sync. Review table corners, timing and ball detections')
        ball, ball_report = reconstruct_ball(*rows, cameras, offset)
        if ball_report['valid_frames'] < 3:
            raise ValueError('Fewer than three usable 3D ball observations; review calibration and detections')
        sync.update(pose=pose_sync, ball=ball_sync, residual_clip_offset_seconds=offset,
                    original_offset_seconds=coarse+offset)
        write_json(out / 'synchronization.json', sync)
        geometry = dict(cameras=[{k: v.tolist() for k, v in c.items()} for c in cameras],
                        offset_b_minus_a_seconds=offset, ball=ball, ball_report=ball_report,
                        calibration=[c[1] for c in calibration], metric_ground_truth_available=False,
                        source_segment_start_seconds=starts[0], body_fps=30,
                        source_sizes=[[i['width'], i['height']] for i in infos],
                        limitations=['Fixed cameras required; camera motion and lens distortion are not compensated.',
                                     'Corner calibration and body depth are estimates, not independent 3D ground truth.'])
        write_json(hmr / 'geometry.json', geometry)
        np.savez_compressed(hmr / 'geometry.npz', poses=np.stack([p[1] for p in poses]),
                            timestamps=poses[0][0], timestamps_b=poses[1][0],
                            **{k: np.stack([c[k] for c in cameras]) for k in ['K', 'R', 't', 'P', 'center']})
        config_path = out / 'serve-config.json'
        write_json(config_path, serve_config(views, videos, infos, offset, out.name))
        run_stage([ROOT / '.venv-serves/bin/python', ROOT / 'scripts/detect_serves.py', '--config', config_path,
                   '--output', out / 'serves', '--max-seconds', count/30, '--device', cfg.get('device', 'auto')],
                  out / 'serves.log', progress, 'Detecting and merging serves')
        device = cfg.get('device', 'auto')
        if device == 'auto':
            import torch
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        for index, video in enumerate(videos, 1):
            run_stage([ROOT / '.venv-hmr2/bin/python', ROOT / 'scripts/run_hmr2.py', '--video', video,
                       '--poses', hmr / f'poses-camera{index}.json', '--output', hmr / f'inference-camera{index}',
                       '--device', device, '--stride', 1, '--max-frames', count],
                      out / f'hmr2-camera{index}.log', progress, f'4D Humans reconstruction · camera {index}')
        run_stage([ROOT / '.venv-hmr2/bin/python', ROOT / 'scripts/fit_hmr2_multiview.py', '--inputs', hmr,
                   '--output', out / 'replay', '--device', device], out / 'body-fit.log', progress, 'Fitting bodies in shared 3D coordinates')
        progress('Packaging synchronized replay and serve review', '')
        scene = package_replay(out, videos, infos, starts, sync)
        report = dict(status='complete', output=str(out), replay=str(out/'replay'),
                      frames=scene['frame_count'], duration_seconds=scene['duration'],
                      serve_candidates=len(scene['serve_events']), ball=ball_report,
                      synchronization=sync, processing_seconds=time.perf_counter()-started)
        write_json(out / 'session-report.json', report)
        progress('Complete', '')
        return report
    except Exception as exc:
        write_json(out / 'session-report.json', dict(status='failed', error=str(exc),
                   synchronization=sync, processing_seconds=time.perf_counter()-started))
        raise

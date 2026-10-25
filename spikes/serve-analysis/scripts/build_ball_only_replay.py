"""Refine a cached two-view session and export an explicitly completed ball track.

Uses existing unannotated source frames/detections, not the burned-in markers in
the linked annotated videos. Does not load player models or body artifacts.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trophy.model import sha256
from trophy.replay.ball_completion import complete_ball_track
from trophy.replay.multiview import fundamental, project, sample_detections, triangulate, viewer_coordinates
from trophy.session import TABLE_CORNERS, calibrate_camera, video_info


def camera(parameters, size):
    width, height = size
    focal = parameters[6]
    K = np.array([[focal, 0, width/2], [0, focal, height/2], [0, 0, 1.]])
    R = cv2.Rodrigues(parameters[:3])[0]
    t = parameters[3:6]
    return dict(K=K, R=R, t=t, P=K @ np.c_[R, t], center=-R.T @ t)


def signed_epipolar(a, b, cameras):
    F = fundamental(*cameras)
    ah, bh = np.c_[a, np.ones(len(a))], np.c_[b, np.ones(len(b))]
    la, lb = bh @ F, ah @ F.T
    return np.sum(bh*lb, axis=1) * np.sqrt(
        1/np.maximum(1e-12, (la[:, :2]**2).sum(1)) +
        1/np.maximum(1e-12, (lb[:, :2]**2).sum(1)))


def build(session, config, output, train_start=4.5, train_end=9.5):
    session, output = Path(session).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(Path(config).read_text())
    sources = [session / f'camera{i}.mp4' for i in [1, 2]]
    infos = [video_info(p) for p in sources]
    sizes = [(v['width'], v['height']) for v in infos]
    rows = [json.loads((session / f'ball-camera{i}/detections.json').read_text()) for i in [1, 2]]
    geometry = json.loads((session / 'hmr2/geometry.json').read_text())
    if not cfg['views'][1]['focal_px']:
        cfg['views'][1]['focal_px'] = geometry['cameras'][1]['K'][0][0]
    initial_cameras = [calibrate_camera(v, info)[0] for v, info in zip(cfg['views'], infos)]
    a, b = rows
    times = np.array([r['timestamp_seconds'] for r in a])
    observed_b = [r for r in b if r['detected']]
    tb = np.array([r['timestamp_seconds'] for r in observed_b])
    ub = np.array([[r['x'], r['y']] for r in observed_b], float)
    interpolate_b = interp1d(tb, ub, axis=0, bounds_error=False, fill_value=np.nan)
    select = np.array([r['detected'] and train_start < r['timestamp_seconds'] < train_end for r in a])
    ta = times[select]
    ua = np.array([[r['x'], r['y']] for r in a], float)[select]
    if len(ta) < 30 or ta.min()-.15 < tb.min() or ta.max()+.15 > tb.max():
        raise ValueError('Need 30 credible training correspondences with temporal support')
    start = np.r_[*[np.r_[cv2.Rodrigues(c['R'])[0].ravel(), c['t'], c['K'][0, 0]]
                     for c in initial_cameras], geometry['offset_b_minus_a_seconds']]
    scales = np.r_[np.tile([.06, .06, .06, .25, .25, .25, 450], 2), .05]
    corners = [np.array(v['table_corners_px'], float) for v in cfg['views']]

    def unpack(p):
        return [camera(p[:7], sizes[0]), camera(p[7:14], sizes[1])]

    def residual(p):
        cameras = unpack(p)
        table = np.concatenate([(project(TABLE_CORNERS, c)-px).ravel()*4
                                for c, px in zip(cameras, corners)])
        epi = signed_epipolar(ua, interpolate_b(ta+p[-1]), cameras)
        return np.r_[table, epi, (p[:-1]-start[:-1])/scales[:-1]*4]

    lo, hi = start-scales*4, start+scales*4
    lo[-1], hi[-1] = -.15, .15
    fits = []
    for offset in [-.06, -.02, .02, .06]:
        seed = start.copy()
        seed[-1] = offset
        fits.append(least_squares(residual, seed, bounds=(lo, hi), loss='soft_l1',
                                  f_scale=8, x_scale=scales, max_nfev=400))
    fit = min(fits, key=lambda f: f.cost)
    cameras, offset = unpack(fit.x), float(fit.x[-1])
    aligned = sample_detections(b, times+offset)
    raw = np.full((len(times), 3), np.nan)
    provenance = []
    epipolar = {'fitted_interval': [], 'held_out_interval': []}
    for i, (row, other) in enumerate(zip(a, aligned)):
        detail = dict(frame_index=i, timestamp_seconds=float(times[i]), status='missing_or_rejected')
        if row['detected'] and other:
            pixels = [[row['x'], row['y']], [other['x'], other['y']]]
            e = abs(float(signed_epipolar(np.array(pixels[:1]), np.array(pixels[1:]), cameras)[0]))
            if times[i] >= train_start:
                epipolar['fitted_interval' if times[i] < train_end else 'held_out_interval'].append(e)
            result = triangulate(pixels, cameras, max_error=25)
            if result and -.1 < result['position'][2] < 2.5 and np.linalg.norm(result['position'][:2]) < 5:
                raw[i] = result['position']
                detail.update(status='triangulated', raw_world_position_m=raw[i].tolist(),
                              image_positions_px=pixels, score=min(row['score'], other['score']),
                              reprojection_errors_px=result['reprojection_errors_px'],
                              camera2_source_frames=other['source_frames'],
                              camera2_temporally_interpolated=other['interpolated'])
        provenance.append(detail)
    completed, statuses, completion = complete_ball_track(times, raw)
    counts = dict(Counter(statuses))
    visible = np.isfinite(completed).all(axis=1)
    valid = np.isfinite(raw).all(axis=1)
    frames = []
    for i, (time, point, status, evidence) in enumerate(zip(times, completed, statuses, provenance)):
        available = bool(np.isfinite(point).all())
        ball = dict(position=viewer_coordinates(point).tolist() if available else None,
                    world_position_m=point.tolist() if available else None,
                    raw_world_position_m=raw[i].tolist() if valid[i] else None,
                    status=status, measured_3d=bool(valid[i]), estimated_gap=available and not bool(valid[i]))
        frames.append(dict(frame_index=i, time=float(time), players=[], ball=ball))
    report = dict(source_urls=['http://127.0.0.1:8508/ball-camera1.mp4',
                              'http://127.0.0.1:8508/ball-camera2.mp4'],
        actual_inputs=[dict(path=str(p), sha256=sha256(p), **info) for p, info in zip(sources, infos)],
        used_cached_unannotated_sources=True, duration_seconds=len(times)/infos[0]['fps'],
        full_frame_count=len(times), triangulated_frames=int(valid.sum()),
        rendered_ball_frames=int(visible.sum()), estimated_gap_frames=int((visible & ~valid).sum()),
        rendered_ball_coverage=float(visible.mean()), status_counts=counts,
        per_second_coverage=[dict(second=k, triangulated=int(valid[(times >= k) & (times < k+1)].sum()),
                                 rendered=int(visible[(times >= k) & (times < k+1)].sum()))
                             for k in range(int(np.ceil(times[-1])))],
        max_triangulation_reprojection_error_px=25, training_interval_seconds=[train_start, train_end],
        epipolar_diagnostics={k: dict(count=len(v), median_px=float(np.median(v)),
                                     p95_px=float(np.percentile(v, 95))) if v else dict(count=0)
                               for k, v in epipolar.items()},
        table_corner_rmse_px=[float(np.sqrt(np.mean((project(TABLE_CORNERS, c)-px)**2)))
                              for c, px in zip(cameras, corners)],
        residual_camera2_minus_camera1_seconds=offset,
        calibration='Inspected full-table marks, square pixels, centered pinhole, no distortion; robust two-view refinement',
        completion=completion, player_renders=False, independently_measured_3d_accuracy=None,
        limitations=['Coverage is not accuracy. Camera geometry and detections are estimates.',
                     'Interpolated/extrapolated positions are display estimates, retained separately from observations.',
                     'Long setup gaps and short endpoint extrapolation use kinematic estimates, not measured contacts.',
                     'Unobserved opening seconds stay unavailable rather than inventing an entire serve.',
                     'Ball spin, drag and racket-contact physics are not measured.'])
    scene = dict(schema='trophy.ball-only-replay.v1', title='Trophy / two-camera ball replay',
                 fps=infos[0]['fps'], duration=len(times)/infos[0]['fps'], frame_count=len(times),
                 axes='raw: X table width, Y table length, Z above tabletop; render: [-Y,X,Z+.76]',
                 sources=[str(p) for p in sources], source_offsets_seconds=[0, offset],
                 cameras=[{k: v.tolist() for k, v in c.items()} for c in cameras],
                 frames=frames, report=report)
    (output/'scene.json').write_text(json.dumps(scene, allow_nan=False, separators=(',', ':')))
    (output/'reconstruction-report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    (output/'raw-triangulation.json').write_text(json.dumps(provenance, indent=2, allow_nan=False))
    (output/'refined-geometry.json').write_text(json.dumps(dict(
        cameras=scene['cameras'], offset_camera2_minus_camera1_seconds=offset,
        table_corner_rmse_px=report['table_corner_rmse_px'],
        training_interval_seconds=report['training_interval_seconds'],
        epipolar_diagnostics=report['epipolar_diagnostics'],
        independently_measured_3d_accuracy=None), indent=2, allow_nan=False))
    with (output/'ball-trajectory.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['frame', 'time_s', 'status', 'triangulated', 'x_m', 'y_m', 'z_m', 'raw_x_m', 'raw_y_m', 'raw_z_m'])
        for i, f in enumerate(frames):
            writer.writerow([i, f['time'], statuses[i], bool(valid[i]),
                             *(completed[i].tolist() if visible[i] else ['', '', '']),
                             *(raw[i].tolist() if valid[i] else ['', '', ''])])
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--train-start', type=float, default=4.5)
    parser.add_argument('--train-end', type=float, default=9.5)
    args = parser.parse_args()
    build(args.session, args.config, args.output, args.train_start, args.train_end)

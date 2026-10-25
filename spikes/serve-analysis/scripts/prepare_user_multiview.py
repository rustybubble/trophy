"""Estimate table-relative geometry for the supplied short handheld rally.

Explicit image measurements initialize the table; static-background homographies
compensate apparent camera motion. Calibration and timing are refined on the
first half of measured ball correspondences, with the second half held out.
This estimates geometry; it is not independent metric ground truth.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trophy.replay.multiview import (fundamental, pose_array, project,
                                    reconstruct_ball, sample_detections)

ROOT = Path('artifacts/user-two-camera')
OUT = ROOT / 'hmr2'
W, L = 1.525, 2.74


def camera(parameters):
    r, t, focal = parameters[:3], parameters[3:6], parameters[6]
    K = np.array([[focal, 0, 960], [0, focal, 540], [0, 0, 1.]])
    R = cv2.Rodrigues(r)[0]
    return dict(K=K, R=R, t=t, P=K @ np.c_[R, t], center=-R.T @ t)


def warp(points, homography):
    points = np.asarray(points)
    shape = points.shape
    return cv2.perspectiveTransform(points.reshape(1, -1, 2).astype(float),
                                    homography).reshape(shape)


def static_mask(image, view):
    mask = np.zeros(image.shape[:2], np.uint8)
    mask[:450] = 255
    if view == 0:
        mask[300:, :800] = 0
        mask[250:, 1350:] = 0
    else:
        mask[280:, 150:750] = 0
    return mask


def reference_motion(video, view, count=180):
    cap = cv2.VideoCapture(str(video))
    ok, first = cap.read()
    if not ok:
        raise ValueError('Missing reference frame')
    gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    points = cv2.goodFeaturesToTrack(gray, 1200, .01, 8,
                                     mask=static_mask(first, view))
    homographies, inliers = [np.eye(3)], [len(points)]
    for _ in range(1, count):
        ok, image = cap.read()
        if not ok:
            raise ValueError('Camera-motion input ended early')
        current = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        target, found, error = cv2.calcOpticalFlowPyrLK(
            gray, current, points, None, winSize=(31, 31), maxLevel=4,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, .01))
        keep = (found[:, 0] > 0) & (error[:, 0] < 20)
        H, mask = cv2.findHomography(points[keep], target[keep], cv2.RANSAC, 1.5)
        if H is None or mask.sum() < 25:
            raise ValueError('Camera motion cannot be estimated reliably')
        homographies.append(H / H[2, 2])
        inliers.append(int(mask.sum()))
    cap.release()
    return np.array(homographies), inliers


def initial_calibration(world, pixels):
    fits = []
    for focal in [900, 1500, 2200]:
        K = camera(np.r_[np.zeros(6), focal])['K']
        ok, rv, tv = cv2.solvePnP(world, pixels, K, None)
        if not ok:
            continue
        def residual(p):
            return (project(world, camera(p)) - pixels).ravel()
        fit = least_squares(residual, np.r_[rv.ravel(), tv.ravel(), focal],
                            bounds=([-20] * 3 + [-100] * 3 + [300],
                                    [20] * 3 + [100] * 3 + [6000]), max_nfev=1000)
        if camera(fit.x)['center'][2] > 0:
            fits.append(fit)
    if not fits:
        raise ValueError('No above-table camera calibration found')
    return min(fits, key=lambda f: np.linalg.norm(f.fun)).x


def signed_epipolar(a, b, cameras):
    F = fundamental(*cameras)
    ah = np.c_[a, np.ones(len(a))]
    bh = np.c_[b, np.ones(len(b))]
    la, lb = bh @ F, ah @ F.T
    error = np.sum(bh * lb, axis=1)
    return error * np.sqrt(1 / np.maximum(1e-12, (la[:, :2] ** 2).sum(1)) +
                           1 / np.maximum(1e-12, (lb[:, :2] ** 2).sum(1)))


def prepare():
    seed = json.loads(Path('configs/user-two-camera-calibration.json').read_text())
    worlds = [np.array(x) for x in seed['world_points']]
    pixels = [np.array(x) for x in seed['pixel_points']]
    initial = [initial_calibration(w, p) for w, p in zip(worlds, pixels)]
    motion = [reference_motion(ROOT / f'camera{i+1}-8s-14s.mp4', i)
              for i in range(2)]
    H = np.stack([m[0] for m in motion])
    poses, detections = [], []
    for view in range(2):
        timestamps, pose, _ = pose_array(OUT / f'poses-camera{view+1}.json')
        rows = json.loads((ROOT / f'blurball-camera{view+1}/detections.json').read_text())
        adjusted = []
        for frame, row in enumerate(rows):
            inverse = np.linalg.inv(H[view, frame])
            pose[frame, :, :, :2] = warp(pose[frame, :, :, :2], inverse)
            row = dict(row)
            if row['detected']:
                row['x'], row['y'] = warp([[row['x'], row['y']]], inverse)[0].tolist()
            adjusted.append(row)
        poses.append(pose)
        detections.append(adjusted)
    a, b = detections
    # Use only the first half of the rally to fit geometry and image timing.
    train = [r for r in a if r['detected'] and r['score'] > .8 and .15 < r['timestamp_seconds'] < 1.5]
    observed_b = [r for r in b if r['detected'] and r['score'] > .8]
    tb = np.array([r['timestamp_seconds'] for r in observed_b])
    interpolate = interp1d(tb, np.array([[r['x'], r['y']] for r in observed_b]),
                           axis=0, bounds_error=False, fill_value='extrapolate')
    ta = np.array([r['timestamp_seconds'] for r in train])
    ua = np.array([[r['x'], r['y']] for r in train])
    start = np.r_[*initial, .04]
    scales = np.r_[np.tile([.05, .05, .05, .25, .25, .25, 300.], 2), .1]

    def residual(p):
        cameras = [camera(p[:7]), camera(p[7:14])]
        table = np.concatenate([((project(w, c) - uv) * weights[:, None]).ravel()
                                for w, uv, c, weights in zip(worlds, pixels, cameras,
                                                            [np.full(4, 3.), np.array([3., 3., 1., 1.])])])
        epipolar = signed_epipolar(ua, interpolate(ta + p[-1]), cameras)
        prior = (p[:-1] - start[:-1]) / scales[:-1]
        return np.r_[table, epipolar * .6, prior]

    lower = start - scales * 3
    upper = start + scales * 3
    lower[-1], upper[-1] = -.06, .14
    fits = []
    for offset in [0., .04, .08, .12]:
        x = start.copy()
        x[-1] = offset
        fit = least_squares(residual, x, bounds=(lower, upper),
                            loss='soft_l1', f_scale=3, x_scale=scales, max_nfev=400)
        fits.append(fit)
    fit = min(fits, key=lambda f: f.cost)
    cameras = [camera(fit.x[:7]), camera(fit.x[7:14])]
    offset = float(fit.x[-1])
    ball, report = reconstruct_ball(a, b, cameras, offset, max_error=8)
    errors = {'fit': [], 'held_out': []}
    paired = sample_detections(b, np.array([r['timestamp_seconds'] for r in a]) + offset)
    for r, other in zip(a, paired):
        if r['detected'] and other:
            value = abs(signed_epipolar([[r['x'], r['y']]], [[other['x'], other['y']]], cameras)[0])
            errors['fit' if r['timestamp_seconds'] < 1.5 else 'held_out'].append(float(value))
    statistics = {k: dict(frames=len(v), median_px=float(np.median(v)),
                           p95_px=float(np.percentile(v, 95))) for k, v in errors.items()}
    result = dict(cameras=[{k: v.tolist() for k, v in c.items()} for c in cameras],
                  offset_b_minus_a_seconds=offset, ball=ball, ball_report=report,
                  image_epipolar_errors=statistics,
                  table_corner_rmse_px=[float(np.sqrt(np.mean((project(w, c) - uv) ** 2)))
                                        for w, uv, c in zip(worlds, pixels, cameras)],
                  motion_inliers=[m[1] for m in motion],
                  metric_ground_truth_available=False,
                  calibration='Estimated from explicit table/half-table image measurements, refined with first-half model ball correspondences.',
                  limitations=['Centered principal point, square pixels and zero lens distortion assumed.',
                               'Background homography assumes dominant camera rotation; camera translation/parallax are not fully modeled.',
                               'Hidden table geometry is initialized from the net/table intersection and background transfer.',
                               'Image reprojection agreement is not independent metric 3D accuracy.',
                               'No synthetic physics path fills missing ball positions.'])
    (OUT / 'geometry.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    np.savez_compressed(OUT / 'geometry.npz', homographies=H, poses=np.stack(poses),
                        timestamps=timestamps, **{k: np.stack([c[k] for c in cameras])
                                                   for k in ['K', 'R', 't', 'P', 'center']})
    # Inspect the full-table and net reprojected into both real source views.
    table = np.array([[-W/2, L/2, 0], [-W/2, -L/2, 0],
                      [W/2, -L/2, 0], [W/2, L/2, 0]], float)
    net = np.array([[-W/2, 0, 0], [-W/2, 0, .1525],
                    [W/2, 0, .1525], [W/2, 0, 0]], float)
    for i, c in enumerate(cameras):
        image = cv2.imread(str(OUT / f'camera{i+1}-frame0.jpg'))
        cv2.polylines(image, [np.round(project(table, c)).astype(np.int32)], True, (0, 255, 0), 2)
        cv2.polylines(image, [np.round(project(net, c)).astype(np.int32)], False, (255, 0, 255), 2)
        cv2.imwrite(str(OUT / f'calibration-overlay{i+1}.jpg'), image)
    print(json.dumps({k: v for k, v in result.items() if k not in ['ball', 'cameras', 'motion_inliers']}, indent=2))


if __name__ == '__main__':
    prepare()

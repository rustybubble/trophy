"""Camera geometry in metres: x along table length, y across, z up."""
import cv2
import numpy as np
from scipy.optimize import least_squares


def calibrate(config):
    points = np.asarray(config['table_corners_world_m'], np.float64)
    pixels = np.asarray(config['table_corners_px'], np.float64)
    if points.shape != (4, 3) or pixels.shape != (4, 2):
        raise ValueError('Exactly four matching table corners are required')
    width, height = config['width'], config['height']
    # Fit a pinhole camera under square-pixel/centered-principal-point assumptions.
    # A single plane still gives weak calibration: this isn't measured intrinsics.
    focal = float(config.get('focal_length_px', 600))
    K = np.array([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1.]])
    ok, rv, tv = cv2.solvePnP(points, pixels, K, np.zeros(5), flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError('Cannot estimate camera pose from the table corners')
    fit_focal = 'focal_length_px' not in config
    initial = np.r_[rv.ravel(), tv.ravel(), focal]
    def residual(v):
        k = K.copy()
        k[0, 0] = k[1, 1] = v[6]
        error = (cv2.projectPoints(points, v[:3], v[3:6], k, None)[0].reshape(-1, 2) - pixels).ravel()
        return np.r_[error, (v[6]-focal)/.001] if not fit_focal else error
    fit = least_squares(residual, initial,
                        bounds=([-20]*3+[-50]*3+[250], [20]*3+[50]*3+[2200]), max_nfev=2000)
    K[0, 0] = K[1, 1] = fit.x[6]
    R = cv2.Rodrigues(fit.x[:3])[0]
    t = fit.x[3:6]
    center = -R.T @ t
    if center[2] < .76:
        raise ValueError('Camera estimated below the tabletop; check corner order')
    return dict(K=K, R=R, t=t, center=center,
                corner_rmse_px=float(np.sqrt(np.mean(fit.fun[:8] ** 2))),
                focal_length_px=float(fit.x[6]), focal_length_assumed=not fit_focal,
                calibration_status='approximate single-plane pinhole fit')


def project(points, camera):
    p = np.atleast_2d(points) @ camera['R'].T + camera['t']
    q = p @ camera['K'].T
    return q[:, :2] / q[:, 2:3]


def ray(pixel, camera):
    direction = camera['R'].T @ np.linalg.solve(camera['K'], np.r_[pixel, 1.])
    return camera['center'], direction / np.linalg.norm(direction)


def on_plane(pixel, z, camera):
    origin, direction = ray(pixel, camera)
    if abs(direction[2]) < 1e-8:
        return None
    distance = (z - origin[2]) / direction[2]
    return origin + distance * direction if distance > 0 else None


def reconstruct_players(raw_frames, camera, smooth=True):
    """Root-relative pretrained MediaPipe skeletons, anchored by visible feet.

    Model world landmarks are camera-oriented, hip-relative metric estimates,
    not globally positioned measurements. Floor intersection anchors translation.
    """
    output = []
    previous_roots = [None, None]
    previous_joints = [None, None]
    for frame in raw_frames:
        people = []
        for pid in range(2):
            pose = next((p for p in frame['players'] if p['id'] == pid), None)
            if pose is None:
                previous_joints[pid] = None
                people.append(dict(id=pid, joints=None, status='missing', confidence=0))
                continue
            lm = np.array(pose['image_landmarks'])
            world = np.array(pose['world_landmarks'])
            relative_camera = world - (world[23] + world[24]) / 2
            relative_world = relative_camera @ camera['R']
            # Anchor the lowest predicted foot to the floor in world space.
            foot_ids = [27, 28, 29, 30, 31, 32]
            foot = min(foot_ids, key=lambda j: relative_world[j, 2])
            floor = on_plane(lm[foot, :2], 0, camera)
            foot_confidence = float(np.mean(lm[[27, 28, 31, 32], 2]))
            foot_anchor_ok = (floor is not None and abs(floor[1]) < 1.5
                              and .5 < -relative_world[foot, 2] < 1.15
                              and foot_confidence > .55)
            if foot_anchor_ok:
                root = floor - relative_world[foot]
                anchor_status = 'estimated_foot_floor_contact'
            else:
                # Behind the table, guessed ankle pixels can project metres into
                # the background. Use an explicit hip-height/playing-zone prior.
                root = on_plane(lm[[23,24], :2].mean(axis=0), .73, camera)
                if root is not None:
                    root[1] = np.clip(root[1], -1.2, 1.2)
                anchor_status = 'hip_height_prior_occluded_feet'
                # Keep uncertain legs anatomical; no gait is generated. Their
                # neutral stance is visibly translucent in the replay.
                for hip, knee, ankle, heel, toe, side in [(23,25,27,29,31,-1),(24,26,28,30,32,1)]:
                    h = relative_world[hip].copy()
                    a = h.copy(); a[0] += side*.12; a[2] = -.73
                    k = (h+a)/2; k[1] -= .06
                    relative_world[knee] = k; relative_world[ankle] = a
                    relative_world[heel] = a + np.array([0,-.05,0])
                    relative_world[toe] = a + np.array([0,.12,0])
            if root is None or np.linalg.norm(root[:2]) > 8:
                people.append(dict(id=pid, joints=None, status='missing', confidence=0))
                continue
            # Temporal filtering smooths model jitter but doesn't invent absent people.
            if smooth and previous_roots[pid] is not None:
                root = .5 * root + .5 * previous_roots[pid]
            joints = relative_world + root
            if smooth and previous_joints[pid] is not None:
                joints = .65 * joints + .35 * previous_joints[pid]
            previous_roots[pid] = root
            previous_joints[pid] = joints
            people.append(dict(id=pid, joints=joints.tolist(), status='monocular_pose_estimate',
                               confidence=pose['confidence'], joint_visibility=lm[:, 2].tolist(),
                               root=root.tolist(), anchor_status=anchor_status,
                               leg_pose_prior=not foot_anchor_ok))
        output.append(people)
    return output

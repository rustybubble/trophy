"""Fit real HMR2 body estimates to both calibrated camera observations.

Uses per-player shape, root translation, joint rotations and temporal priors.
Ball reconstruction is loaded independently and never drives the body fit.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from scipy.interpolate import interp1d
from scipy.spatial.transform import Rotation
import torch
from smplx.lbs import batch_rodrigues

from trophy.replay.hmr2 import CheckpointBody
from trophy.replay.multiview import viewer_coordinates
from trophy.replay.body_initialization import initialize_body_roots

OUT = Path('artifacts/user-two-camera/hmr2')
SMPL_IDS = [16, 17, 18, 19, 20, 21, 1, 2, 4, 5, 7, 8]
MP_IDS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]


def rotation_mean(a, b, weight=.5):
    return Rotation.from_matrix(np.stack([a, b])).mean(weights=[1-weight, weight]).as_matrix()


def fit(args):
    started = time.perf_counter()
    device = args.device
    if device == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('Apple GPU unavailable; no silent CPU substitution')
    inputs = Path(getattr(args, 'inputs', OUT))
    geometry = json.loads((inputs / 'geometry.json').read_text())
    arrays = np.load(inputs / 'geometry.npz')
    predictions = [np.load(inputs / f'inference-camera{i}/predictions.npz') for i in [1, 2]]
    buffers = np.load(inputs / 'inference-camera1/body-buffers.npz')
    body = CheckpointBody({'smpl.' + k: torch.from_numpy(buffers[k]) for k in buffers.files}).to(device)
    cameras = [{k: arrays[k][v] for k in ['K', 'R', 't', 'P', 'center']} for v in range(2)]
    offset = geometry['offset_b_minus_a_seconds']
    frame_indices = np.unique(predictions[0]['frame_index'])
    times = arrays['timestamps'][frame_indices]
    # Fit only the time shared by both players in both views. Missing bodies
    # must not cause extrapolated meshes before/after an observed track.
    for view, prediction in enumerate(predictions):
        for player in range(2):
            observed = prediction['time'][prediction['player_id'] == player]
            if len(observed) < 2:
                raise ValueError(f'Camera {view+1}, player {player+1}: need at least two body observations; review player regions')
            query = arrays['timestamps'][frame_indices] + (offset if view else 0)
            frame_indices = frame_indices[(query >= observed.min()) & (query <= observed.max())]
    times = arrays['timestamps'][frame_indices]
    count = len(times)
    if count < 3:
        raise ValueError('Need at least three overlapping body frames after camera synchronization')
    local = np.zeros((count, 2, 24, 3, 3), np.float32)
    shapes = np.zeros((2, 10), np.float32)
    target = np.empty((2, count, 2, len(SMPL_IDS), 3), np.float32)
    aligned_pose = [arrays['poses'][0, frame_indices],
                    interp1d(arrays['timestamps_b'] if 'timestamps_b' in arrays else arrays['timestamps'], arrays['poses'][1], axis=0,
                             bounds_error=False, fill_value=np.nan)(times + offset)]
    roots, root_source_array, root_observed = initialize_body_roots(times, aligned_pose, cameras)
    root_sources = root_source_array.ravel().tolist()
    for view in range(2):
        target[view] = aligned_pose[view][:, :, MP_IDS]
    for player in [0, 1]:
        view_parameters = []
        all_shapes = []
        for view, prediction in enumerate(predictions):
            keep = prediction['player_id'] == player
            tt = prediction['time'][keep]
            matrices = prediction['rotations'][keep].copy()
            matrices[:, 0] = cameras[view]['R'].T @ matrices[:, 0]
            query = times + (offset if view else 0)
            # Project interpolated matrices back onto SO(3) after timestamp alignment.
            blended = interp1d(tt, matrices, axis=0, bounds_error=False,
                               fill_value=np.nan)(query)
            u, _, vt = np.linalg.svd(blended)
            orientation = u @ vt
            negative = np.linalg.det(orientation) < 0
            u[negative, :, -1] *= -1
            orientation = u @ vt
            view_parameters.append(orientation)
            all_shapes.append(prediction['betas'][keep])
        shapes[player] = np.median(np.concatenate(all_shapes), axis=0).clip(-3, 3)
        for frame in range(count):
            # Both views contribute; the full-body side view receives more weight
            # for the near player whose legs are cut off in camera 2.
            weight = .5 if player == 0 else .25
            for joint in range(24):
                local[frame, player, joint] = rotation_mean(
                    view_parameters[0][frame, joint], view_parameters[1][frame, joint], weight)
    initial_axis = Rotation.from_matrix(local.reshape(-1, 3, 3)).as_rotvec().reshape(count, 2, 24, 3).astype(np.float32)
    pose = torch.tensor(initial_axis, device=device, requires_grad=True)
    root = torch.tensor(roots, device=device, requires_grad=True)
    shape = torch.tensor(shapes, device=device, requires_grad=True)
    reference_rotation = torch.tensor(local, device=device)
    reference_shape = torch.tensor(shapes, device=device)
    target_tensor = torch.tensor(np.nan_to_num(target[..., :2]), device=device)
    visibility = np.nan_to_num(target[..., 2]).clip(0, 1)
    # Invisible or frame-external joints must not drag the body toward model guesses.
    weights = torch.tensor(np.where(visibility > .45, visibility ** 3, 0), device=device)
    K = torch.tensor(arrays['K'].astype(np.float32), device=device)
    R = torch.tensor(arrays['R'].astype(np.float32), device=device)
    translation = torch.tensor(arrays['t'].astype(np.float32), device=device)

    def forward():
        rotation = batch_rodrigues(pose.reshape(-1, 3)).reshape(count*2, 24, 3, 3)
        beta = shape[None].expand(count, -1, -1).reshape(count*2, 10)
        vertices, joints = body(beta, rotation)
        pelvis = joints[:, :1]
        vertices = (vertices - pelvis).reshape(count, 2, -1, 3) + root[:, :, None]
        joints = (joints - pelvis).reshape(count, 2, -1, 3) + root[:, :, None]
        observed = joints[:, :, SMPL_IDS]
        camera_points = torch.einsum('vij,fpqj->vfpqi', R, observed) + translation[:, None, None, None]
        homogeneous = torch.einsum('vij,vfpqj->vfpqi', K, camera_points)
        pixels = homogeneous[..., :2] / homogeneous[..., 2:].clamp(min=.1)
        return vertices, joints, rotation.reshape(count, 2, 24, 3, 3), pixels

    with torch.no_grad():
        _, _, _, initial_pixels = forward()
        before = np.linalg.norm(initial_pixels.cpu().numpy() - np.nan_to_num(target[..., :2]), axis=-1)
    optimizer = torch.optim.Adam([pose, root, shape], lr=.015)
    history = []
    for step in range(args.steps):
        optimizer.zero_grad()
        vertices, joints, rotation, pixels = forward()
        difference = (pixels - target_tensor) / 10
        robust = torch.sqrt(1 + difference.square().sum(-1)) - 1
        image_loss = (robust * weights).sum() / weights.sum().clamp(min=1)
        pose_prior = (rotation[:, :, 1:] - reference_rotation[:, :, 1:]).square().mean()
        global_prior = (rotation[:, :, :1] - reference_rotation[:, :, :1]).square().mean()
        temporal_root = (root[2:] - 2*root[1:-1] + root[:-2]).square().mean()
        temporal_pose = (rotation[2:] - 2*rotation[1:-1] + rotation[:-2]).square().mean()
        shape_prior = (shape - reference_shape).square().mean()
        minimum_z = vertices[..., 2].min(dim=2).values
        floor_penetration = torch.relu(-.76 - minimum_z).square().mean()
        # Floor contact is a weak body-placement prior, not measured contact timing.
        floor_contact = (minimum_z + .76).square().mean()
        loss = (image_loss + .4*pose_prior + .15*global_prior + .05*shape_prior +
                80*temporal_root + .5*temporal_pose + 20*floor_penetration + .2*floor_contact)
        loss.backward()
        optimizer.step()
        with torch.no_grad():
            shape.clamp_(-3, 3)
        if step % 25 == 0 or step == args.steps-1:
            row = dict(step=step, loss=float(loss.detach().cpu()), image_loss=float(image_loss.detach().cpu()))
            history.append(row)
            print(json.dumps(row), flush=True)
    with torch.no_grad():
        vertices, joints, rotation, pixels = forward()
        vertices = vertices.cpu().numpy()
        joints = joints.cpu().numpy()
        after = np.linalg.norm(pixels.cpu().numpy() - np.nan_to_num(target[..., :2]), axis=-1)
    visible = visibility > .65
    stats = lambda values: dict(count=int(len(values)), median_px=float(np.median(values)) if len(values) else None, p95_px=float(np.percentile(values, 95)) if len(values) else None)
    report = dict(method='Official HMR2 initialization; two-view visible-landmark fit of SMPL pose, per-player shape and root, with temporal and weak floor priors',
                  device=device, frames=count, duration_seconds=float(times[-1]),
                  source_segment_start_seconds=geometry.get('source_segment_start_seconds', 8), steps=args.steps,
                  reprojection_before=stats(before[visible]), reprojection_after=stats(after[visible]),
                  per_view_after=[stats(after[v][visible[v]]) for v in range(2)],
                  root_initialization_counts={k: root_sources.count(k) for k in set(root_sources)},
                  root_anchor_frames_per_player=root_observed.sum(axis=0).tolist(),
                  root_initialization_policy='Use valid two-camera hip anchors across the clip; interpolate or use nearest anchor only as optimizer initialization. Final roots fit current visible image landmarks.',
                  human_3d_ground_truth_available=False, phalp_tracker_used=False,
                  independent_3d_accuracy_measured=False,
                  elapsed_seconds=time.perf_counter()-started, optimization=history,
                  limitations=['Body image landmarks are model estimates, not manually labeled ground truth.',
                               'Camera intrinsics and motion are approximate; image fit does not prove metric accuracy.',
                               'Hidden joints, shape under clothing and floor contact remain estimates.',
                               'Rackets and ball/racket contact are not reconstructed by HMR2.'])
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    fitted_roots = root.detach().cpu().numpy()
    np.savez_compressed(output / 'fitted-bodies.npz', vertices=vertices, joints=joints,
                        rotations=rotation.detach().cpu().numpy(), roots=fitted_roots,
                        betas=shape.detach().cpu().numpy(), frame_indices=frame_indices, times=times,
                        faces=buffers['faces_tensor'])
    viewer_vertices = viewer_coordinates(vertices).astype('<f4')
    viewer_vertices.tofile(output / 'vertices.f32')
    buffers['faces_tensor'].astype('<u4').tofile(output / 'faces.u32')
    frames = [dict(frame_index=int(idx), time=float(t), ball=geometry['ball'][idx],
                   player_roots=viewer_coordinates(fitted_roots[i]).tolist(),
                   root_initialization_sources=root_source_array[i].tolist(),
                   root_anchor_observed=root_observed[i].tolist())
              for i, (idx, t) in enumerate(zip(frame_indices, times))]
    scene = dict(type='HMR2 + measured two-view ball reconstruction',
                 title=geometry.get('title', 'Your rally · 4D Humans + BlurBall'), fps=geometry.get('body_fps', 30), duration=float(times[-1]),
                 frame_count=count, vertex_count=int(vertices.shape[2]), players=2,
                 face_count=int(len(buffers['faces_tensor'])), frames=frames,
                 source_offsets_seconds=[0, offset], source_segment_start_seconds=geometry.get('source_segment_start_seconds', 8),
                 start_time=float(times[0]), source_sizes=geometry.get('source_sizes', [[1920, 1080], [1920, 1080]]),
                 axes='x table length; y table width; z up; floor at zero', units='metres',
                 report=report, geometry_report={k: v for k, v in geometry.items()
                                               if k not in ['ball', 'motion_inliers']})
    (output / 'scene.json').write_text(json.dumps(scene, indent=2, allow_nan=False))
    (output / 'body-fit-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'optimization'}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', default='artifacts/user-two-camera/reconstruction')
    p.add_argument('--inputs', default=str(OUT), help='Geometry and per-camera HMR2 inference directory')
    p.add_argument('--device', choices=['mps', 'cpu'], default='mps')
    p.add_argument('--steps', type=int, default=250)
    fit(p.parse_args())

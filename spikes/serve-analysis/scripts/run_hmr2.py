"""Run the official HMR2 core on real player crops; no training or pose fixtures."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import torch
from trophy.replay.hmr2 import HMR2Inference, person_box, preprocess_person


def run(args):
    if args.device == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('MPS is unavailable; no silent CPU substitution')
    if args.stride < 1 or args.batch_size < 1:
        raise ValueError('Stride and batch size must be positive')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'predictions.npz').exists():
        raise ValueError('Predictions already exist; choose a new output directory')
    start = time.perf_counter()
    model = HMR2Inference(args.checkpoint, args.config, args.device)
    poses = json.loads(Path(args.poses).read_text())
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise ValueError('Video cannot be opened')
    pending, records, latencies = [], [], []

    def flush():
        if not pending:
            return
        batch = torch.stack([p['image'] for p in pending]).to(args.device)
        if args.device == 'mps':
            torch.mps.synchronize()
        t = time.perf_counter()
        with torch.inference_mode():
            prediction = model(batch)
        if args.device == 'mps':
            torch.mps.synchronize()
        latencies.append(time.perf_counter() - t)
        values = {k: v.detach().cpu().numpy() for k, v in prediction.items()}
        for k, record in enumerate(pending):
            record.pop('image')
            record.update({name: values[name][k] for name in values})
            records.append(record)
        pending.clear()
        print(f'HMR2 inferred {len(records)} person frames', flush=True)

    try:
        for index, frame_pose in enumerate(poses['frames'][:args.max_frames]):
            ok, bgr = cap.read()
            if not ok:
                raise ValueError('Input video ended before its pose timestamps')
            if index % args.stride:
                continue
            for person in frame_pose['players']:
                box = person_box(person['image_landmarks'], bgr.shape[1], bgr.shape[0])
                tensor, center, size = preprocess_person(bgr, box)
                pending.append(dict(image=tensor, frame_index=index,
                                    time=frame_pose['timestamp_seconds'], player_id=person['id'],
                                    box=box, center=center, size=size))
                if len(pending) >= args.batch_size:
                    flush()
        flush()
    finally:
        cap.release()
    keys = ['rotations', 'betas', 'camera', 'vertices', 'joints', 'box',
            'center', 'size', 'frame_index', 'time', 'player_id']
    np.savez_compressed(out / 'predictions.npz',
                        **{k: np.array([r[k] for r in records]) for k in keys},
                        faces=model.body.faces_tensor.detach().cpu().numpy())
    # Save exact public checkpoint buffers for differentiable two-view fitting.
    np.savez_compressed(out / 'body-buffers.npz',
                        **{k: getattr(model.body, k).detach().cpu().numpy()
                           for k in model.body.REQUIRED})
    report = dict(model='4D Humans HMR2.0b official ViT-H + SMPL transformer head',
                  source_commit='efe18deff163b29dff87ddbd575fa29b716a356c',
                  checkpoint_sha256=model.checkpoint_sha256,
                  checkpoint=str(Path(args.checkpoint).resolve()),
                  source_video=str(Path(args.video).resolve()), device=args.device,
                  stride=args.stride, source_fps=poses['report']['fps'],
                  person_frames=len(records), batch_seconds=latencies,
                  elapsed_seconds=time.perf_counter()-start,
                  labels_used=False, phalp_tracker_used=False,
                  bounding_boxes='Per-view pretrained MediaPipe image landmarks; explicit player crop IDs',
                  body_model='Exact SMPL buffers embedded in the official released checkpoint',
                  camera_parameters='HMR2 monocular camera estimates; not shared-world calibration')
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video', required=True)
    p.add_argument('--poses', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--checkpoint', default='weights/hmr2-assets/logs/train/multiruns/hmr2/0/checkpoints/epoch=35-step=1000000.ckpt')
    p.add_argument('--config', default='weights/hmr2-assets/model_config.yaml')
    p.add_argument('--device', choices=['mps', 'cpu'], default='mps')
    p.add_argument('--stride', type=int, default=2)
    p.add_argument('--max-frames', type=int, default=180)
    p.add_argument('--batch-size', type=int, default=4)
    run(p.parse_args())

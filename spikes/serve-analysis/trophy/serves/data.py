"""Timestamp-preserving low-resolution video samples for event spotting."""
from pathlib import Path
import hashlib
import json

import av
import cv2
import numpy as np
import torch

FPS = 15
HEIGHT, WIDTH = 128, 224
CLIP_FRAMES = 48


def resize_rgb(rgb):
    h, w = rgb.shape[:2]
    scale = min(WIDTH / w, HEIGHT / h)
    rw, rh = round(w * scale), round(h * scale)
    result = np.full((HEIGHT, WIDTH, 3), 114, np.uint8)
    x, y = (WIDTH - rw) // 2, (HEIGHT - rh) // 2
    result[y:y+rh, x:x+rw] = cv2.resize(rgb, (rw, rh), interpolation=cv2.INTER_AREA)
    return result


def read_samples(video, start=0., end=None, fps=FPS):
    """Use actual decoded PTS, not reported frame number, for sample timing."""
    if start < 0 or (end is not None and end <= start) or fps <= 0:
        raise ValueError('Invalid sampling interval/rate')
    images, times = [], []
    with av.open(str(video), timeout=(30., 60.)) as container:
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'
        stream.codec_context.thread_count = 2
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else 0.
        if start > 0:
            container.seek(int((start + origin) / stream.time_base), stream=stream, backward=True)
        next_time = start
        for frame in container.decode(stream):
            if frame.pts is None:
                raise ValueError('Serve video requires source presentation timestamps')
            stamp = float(frame.pts * stream.time_base) - origin
            if end is not None and stamp >= end - 1e-8:
                break
            if stamp + 1e-8 < next_time:
                continue
            images.append(resize_rgb(frame.to_ndarray(format='rgb24')))
            times.append(stamp)
            # Retain missing sampling slots in timestamps; never duplicate frames.
            next_time = start + (int(np.floor((stamp - start) * fps + 1e-6)) + 1) / fps
    if not times:
        raise ValueError(f'No timestamped frames in {video} at {start}')
    return np.stack(images), np.asarray(times, dtype=np.float64)


def cache_signature(video, end):
    path=Path(video).expanduser().resolve();stat=path.stat()
    return dict(path=str(path),size=stat.st_size,mtime_ns=stat.st_mtime_ns,
                end_seconds=end,sampling_fps=FPS,width=WIDTH,height=HEIGHT,preprocess='rgb-area-letterbox-v1')


def cached_samples(video, end, cache_dir):
    signature=cache_signature(video,end)
    key=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    directory=Path(cache_dir);directory.mkdir(parents=True,exist_ok=True)
    target=directory/f'{key}.npz'
    if target.exists():
        with np.load(target,allow_pickle=False) as data:
            if json.loads(str(data['signature']))!=signature:
                raise ValueError('Sample cache identity mismatch')
            return data['images'],data['times']
    images,times=read_samples(video,end=end)
    temporary=target.with_suffix('.partial.npz')
    np.savez_compressed(temporary,images=images,times=times,signature=json.dumps(signature,sort_keys=True))
    temporary.replace(target)
    return images,times


def tensor_frames(images, device='cpu'):
    x = torch.from_numpy(np.ascontiguousarray(images)).to(device=device, dtype=torch.float32)
    x = x.permute(0, 3, 1, 2) / 255.
    mean = x.new_tensor([.485, .456, .406])[None, :, None, None]
    std = x.new_tensor([.229, .224, .225])[None, :, None, None]
    # MPS BatchNorm backward rejects some channels-last strides produced by
    # NHWC-to-NCHW permutes. Use the same contiguous layout in train/inference.
    return ((x - mean) / std).contiguous()


def read_events(path, source_fps=120.):
    events = []
    for key, value in json.loads(Path(path).read_text()).items():
        tokens = str(value).split()[0].split('_')
        if len(tokens) >= 3 and tokens[0] in ('left', 'right') and tokens[1] in ('forehand', 'backhand'):
            kind = 'serve' if tokens[2] == 'serve' else 'stroke'
            events.append(dict(time=int(key) / source_fps, side=tokens[0], kind=kind,
                               source_frame=int(key), source_label=value))
    return sorted(events, key=lambda e: e['time'])


def frame_targets(times, events, radius=.14):
    """Unknown/unlabeled stretches are backgrounds only under the dataset policy."""
    targets = np.zeros(len(times), dtype=np.int64)
    nearest = np.full(len(times), np.inf)
    for event in events:
        distance = np.abs(times - event['time'])
        selected = (distance <= radius) & (distance < nearest)
        label = (1 if event['kind'] == 'serve' else 3) + int(event['side'] == 'right')
        targets[selected], nearest[selected] = label, distance[selected]
    return targets

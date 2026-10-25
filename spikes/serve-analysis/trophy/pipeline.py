"""Shared bounded-memory clip workflow for the CLI and local UI."""
from collections import deque
import csv
from fractions import Fraction
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import tempfile
import time

import av
import cv2
import imageio_ffmpeg
import numpy as np
import torch

from .model import DEFAULT_WEIGHTS, Predictor, UPSTREAM_COMMIT, decode_heatmap, preprocess

FIELDS = ['frame_index', 'timestamp_seconds', 'unique_frame_index', 'duplicate_of_frame',
          'x', 'y', 'score', 'heatmap_peak', 'detected', 'status', 'component_mass',
          'blur_angle_degrees', 'blur_length_px', 'temporal_contexts']


def window_indices(n):
    """No padding or fabricated temporal neighbors, including at either boundary."""
    return [tuple(range(i, i + 3)) for i in range(max(0, n - 2))]


def capture(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f'Cannot decode video: {path}')
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    return cap


class Encoder:
    def __init__(self, path, width, height, fps):
        self.path = Path(path)
        self.log = tempfile.TemporaryFile()
        rate = str(Fraction(fps).limit_denominator(100000))
        self.command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                        '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}',
                        '-framerate', rate, '-i', 'pipe:0', '-an', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(path)]
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)

    def write(self, frame):
        try:
            self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError('Video encoding failed: ' + self.error()) from e

    def error(self):
        self.log.seek(0)
        return self.log.read().decode(errors='replace')

    def close(self):
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                try:
                    self.proc.stdin.close()
                except BrokenPipeError:
                    pass
            code = self.proc.wait(timeout=120)
            if code or not self.path.is_file() or self.path.stat().st_size == 0:
                raise RuntimeError('Video encoding failed: ' + self.error())
        finally:
            self.log.close()

    def abort(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except BrokenPipeError:
                pass
        self.log.close()


def verify_video(path, expected_frames, fps):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        actual = sum(1 for _ in container.decode(video=0))
        if actual != expected_frames:
            raise RuntimeError(f'Encoded frame count mismatch: {actual} != {expected_frames}')
        if abs(float(stream.average_rate) - fps) > .001:
            raise RuntimeError('Encoded frame rate differs from source')
        if stream.codec_context.name != 'h264':
            raise RuntimeError('Output is not browser-compatible H.264')
        return dict(codec='h264', pixel_format=stream.codec_context.pix_fmt, frames=actual,
                    fps=float(stream.average_rate), width=stream.width, height=stream.height)


def annotate(frame, row, trail):
    if not row['detected']:
        trail.clear()
    else:
        point = (round(row['x']), round(row['y']))
        trail.append(point)
        if len(trail) > 1:
            cv2.polylines(frame, [np.array(trail, np.int32)], False, (0, 210, 255), 2, cv2.LINE_AA)
        angle = math.radians(row['blur_angle_degrees'])
        half = row['blur_length_px'] / 2
        delta = np.array([math.cos(angle), math.sin(angle)]) * half
        a, b = np.array(point) - delta, np.array(point) + delta
        cv2.line(frame, tuple(np.rint(a).astype(int)), tuple(np.rint(b).astype(int)), (255, 100, 0), 2)
        cv2.circle(frame, point, 9, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.drawMarker(frame, point, (0, 255, 0), cv2.MARKER_CROSS, 12, 1)
    text = f"#{row['frame_index']}  {row['status']}"
    if row['detected']:
        text += f"  peak {row['score']:.2f}  blur {row['blur_length_px']:.1f}px"
    cv2.putText(frame, text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def analyze(input_path, output_dir, *, weights=DEFAULT_WEIGHTS, device='auto', threshold=.7,
            max_frames=600, max_duration=None, progress=None, photometric='rgb'):
    start_all = time.perf_counter()
    path, out = Path(input_path).expanduser().resolve(), Path(output_dir).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Input video unavailable: {path}')
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError('threshold must be between 0 and 1 (exclusive)')
    if photometric not in ('rgb', 'max-channel-gray'):
        raise ValueError('photometric must be rgb or max-channel-gray')
    if max_frames is not None and max_frames <= 0:
        raise ValueError('max_frames must be positive')
    if max_duration is not None and (not math.isfinite(max_duration) or max_duration <= 0):
        raise ValueError('max_duration must be positive')
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Output directory must be empty: {out}')
    out.mkdir(parents=True, exist_ok=True)
    cap = capture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps <= 0:
        cap.release()
        raise ValueError('Video has no valid playback frame rate')
    source_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    rotation = cap.get(cv2.CAP_PROP_ORIENTATION_META)
    limit = max_frames or math.inf
    if max_duration is not None:
        limit = min(limit, max(1, math.ceil(max_duration * fps - 1e-8)))
    expected = min(source_count, limit) if source_count > 0 else limit
    callback = progress or (lambda stage, done, total: None)
    callback('Loading pretrained model', 0, 1)
    t = time.perf_counter()
    try:
        predictor = Predictor(weights, device)
    except Exception:
        cap.release()
        raise
    setup_seconds = time.perf_counter() - t
    timings = dict(decode=0., preprocess=0., input_transfer_and_dispatch=0., model=0.,
                   output_transfer=0., postprocess=0., render_encode=0., export_verify=0.)
    buffer = deque(maxlen=3)
    unique = []
    frames = []
    previous = None
    last_unique_source = None
    latencies = []
    warmup_seconds = 0.
    width = height = 0
    try:
        while len(frames) < limit:
            t = time.perf_counter()
            ok, bgr = cap.read()
            stamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            timings['decode'] += time.perf_counter() - t
            if not ok:
                break
            h, w = bgr.shape[:2]
            if width and (w, h) != (width, height):
                raise ValueError('Variable-resolution video is unsupported')
            width, height = w, h
            i = len(frames)
            if not math.isfinite(stamp) or (i > 0 and stamp <= frames[-1]['timestamp_seconds']):
                stamp = i / fps
            t = time.perf_counter()
            duplicate = previous is not None and np.array_equal(bgr, previous)
            if not duplicate:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                if photometric == 'max-channel-gray':
                    # Experimental color-domain adaptation. Applied to every
                    # pixel, without locating the ball or creating detections.
                    rgb = np.repeat(rgb.max(axis=2)[..., None], 3, axis=2)
                processed, inverse = preprocess(rgb)
                uid = len(unique)
                unique.append(dict(best=None, peak=0., contexts=0))
                buffer.append((uid, processed))
                last_unique_source = i
            else:
                uid = len(unique) - 1
            frames.append(dict(frame_index=i, timestamp_seconds=stamp, unique_frame_index=uid,
                               duplicate_of_frame=last_unique_source if duplicate else None))
            previous = bgr
            timings['preprocess'] += time.perf_counter() - t
            if not duplicate and len(buffer) == 3:
                inputs = [item[1] for item in buffer]
                if predictor.warmup_ms is None:
                    warmup_start = time.perf_counter()
                    predictor.warmup(inputs)
                    warmup_seconds = time.perf_counter() - warmup_start
                t = time.perf_counter()
                maps, ms, transfer_ms = predictor.predict(inputs)
                elapsed = time.perf_counter() - t
                timings['model'] += ms / 1000
                timings['output_transfer'] += transfer_ms / 1000
                timings['input_transfer_and_dispatch'] += max(0, elapsed - (ms + transfer_ms) / 1000)
                latencies.append(ms)
                t = time.perf_counter()
                for head, (j, _) in enumerate(buffer):
                    candidates, peak = decode_heatmap(maps[head], inverse, width, height, threshold)
                    u = unique[j]
                    u['contexts'] += 1
                    u['peak'] = max(u['peak'], peak)
                    for candidate in candidates:
                        if u['best'] is None or candidate['component_mass'] > u['best']['component_mass']:
                            u['best'] = candidate
                timings['postprocess'] += time.perf_counter() - t
            callback('Analyzing', len(frames), expected)
    finally:
        cap.release()
    if not frames:
        raise ValueError('Video contains no decodable frames')
    rows = []
    for frame in frames:
        u = unique[frame['unique_frame_index']]
        best = u['best']
        row = {**frame, 'x': None, 'y': None, 'score': None, 'component_mass': None,
               'blur_angle_degrees': None, 'blur_length_px': None,
               'heatmap_peak': u['peak'] if u['contexts'] else None, 'detected': best is not None,
               'status': 'detected' if best else ('missing' if u['contexts'] else 'insufficient_temporal_context'),
               'temporal_contexts': u['contexts']}
        if best:
            row.update(best)
        rows.append(row)
    t = time.perf_counter()
    # Write and verify in a temporary directory; failed encodes are never published as success.
    with tempfile.TemporaryDirectory(prefix='.trophy-', dir=out) as tmp:
        tmp = Path(tmp)
        cap = capture(path)
        encoders = []
        try:
            encoders.append(Encoder(tmp / 'original.mp4', width, height, fps))
            encoders.append(Encoder(tmp / 'annotated.mp4', width, height, fps))
            trail = deque(maxlen=8)
            for i, row in enumerate(rows):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Source changed or failed during render pass')
                encoders[0].write(frame)
                encoders[1].write(annotate(frame.copy(), row, trail))
                callback('Rendering', i + 1, len(rows))
            for encoder in encoders:
                encoder.close()
        except Exception:
            for encoder in encoders:
                if not encoder.log.closed:
                    encoder.abort()
            raise
        finally:
            cap.release()
        timings['render_encode'] = time.perf_counter() - t
        t = time.perf_counter()
        video_info = verify_video(tmp / 'annotated.mp4', len(rows), fps)
        verify_video(tmp / 'original.mp4', len(rows), fps)
        (tmp / 'detections.json').write_text(json.dumps(rows, indent=2, allow_nan=False))
        with (tmp / 'detections.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        timings['export_verify'] = time.perf_counter() - t
        elapsed = time.perf_counter() - start_all
        detected = sum(r['detected'] for r in rows)
        versions = {p: importlib.metadata.version(p) for p in
                    ['torch', 'numpy', 'opencv-python-headless', 'av', 'streamlit', 'imageio-ffmpeg']}
        versions['ffmpeg'] = imageio_ffmpeg.get_ffmpeg_version()
        report = dict(input=str(path), requested_device=device, device=predictor.device,
                      model_execution_verified=bool(latencies),
                      mps_model_forward_verified=predictor.device == 'mps' and bool(latencies),
                      model_forward_cpu_fallback_enabled=False,
                      cpu_stages=['decode', 'RGB conversion/resize/normalization', 'connected components/PCA', 'render', 'H.264 encode'],
                      software=versions, python=platform.python_version(), platform=platform.platform(),
                      architecture=platform.machine(), upstream_commit=UPSTREAM_COMMIT,
                      weights_sha256=predictor.weight_sha256,
                      source=dict(width=width, height=height, fps=fps, reported_frame_count=source_count,
                                  rotation_metadata_degrees=rotation, coordinates='display-oriented source pixels',
                                  timestamp_policy='decoder PTS seconds; frame_index/fps if missing or nonmonotonic'),
                      analyzed_frame_count=len(rows), unique_frame_count=len(unique),
                      exact_duplicate_frames=len(rows) - len(unique),
                      detected_frame_count=detected, detection_coverage=detected / len(rows),
                      coverage_is_accuracy=False, threshold=threshold, temporal_window=3, temporal_step=1,
                      photometric_preprocessing=photometric,
                      inference_windows=len(latencies), warmup_model_ms=predictor.warmup_ms,
                      warmup_total_seconds=warmup_seconds,
                      model_setup_seconds=setup_seconds,
                      inference_latency_ms=dict(mean=float(np.mean(latencies)) if latencies else None,
                                                p50=float(np.percentile(latencies, 50)) if latencies else None,
                                                p95=float(np.percentile(latencies, 95)) if latencies else None),
                      model_windows_per_second=len(latencies) / timings['model'] if timings['model'] else None,
                      stage_seconds=timings, total_seconds=elapsed, end_to_end_processing_fps=len(rows) / elapsed,
                      output_video=video_info,
                      notes=['Model-only latency includes sigmoid and device synchronization; excludes transfers and warmup.',
                             'End-to-end includes model load, one real-window warmup, two decode passes, two video encodes and verification.',
                             'Scores are heatmap peaks, not calibrated detection probabilities; candidates rank by upstream component mass.',
                             'Blur is inferred from thresholded heatmap shape, not a separately calibrated blur head.',
                             'Exact duplicate frames reuse model evidence from the same pixels; near duplicates are retained.',
                             'CFR previews use source reported average FPS; variable-FPS source timestamps remain in JSON/CSV. Audio omitted.',
                             'Portrait uses full-frame letterbox; portrait accuracy has not been established.'])
        (tmp / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
        for file in tmp.iterdir():
            file.replace(out / file.name)
    callback('Complete', len(rows), len(rows))
    return report

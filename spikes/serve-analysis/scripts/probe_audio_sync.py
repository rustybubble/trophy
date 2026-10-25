"""Experimental audio initialization + visual refinement, without reference labels.

This diagnostic does not change the demo's production synchronization path.
Injected shifts exercise clock recovery on existing recordings, not new footage.
"""
import argparse
import json
import sys
from pathlib import Path

import av
import numpy as np
from scipy.signal import butter, correlate, correlation_lags, sosfilt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trophy.replay.multiview import load_camera, reconstruct_ball, synchronize_ball

ENVELOPE_HZ = 200


def audio_envelope(path, max_seconds=60):
    """Read the first audio channel mix, retaining the stream's timestamp origin."""
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError(f'No audio stream: {path}')
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
        parts = []
        first = None
        samples = 0
        for frame in container.decode(container.streams.audio[0]):
            if first is None:
                if frame.time is None:
                    raise ValueError('Audio timestamp missing; cannot align video clocks')
                first = float(frame.time)
            for converted in resampler.resample(frame):
                part = converted.to_ndarray().ravel()
                parts.append(part)
                samples += len(part)
            if samples >= max_seconds * 16000:
                break
        for converted in resampler.resample(None):
            parts.append(converted.to_ndarray().ravel())
    if not parts:
        raise ValueError('No decoded audio samples')
    signal = np.concatenate(parts)[:max_seconds * 16000]
    signal = sosfilt(butter(3, [700, 6000], btype='bandpass',
                            fs=16000, output='sos'), signal)
    block = 16000 // ENVELOPE_HZ
    signal = signal[:len(signal) // block * block].reshape(-1, block)
    envelope = np.log1p(100 * np.sqrt(np.mean(signal * signal, axis=1)))
    envelope -= envelope.mean()
    if len(envelope) < ENVELOPE_HZ or np.std(envelope) < 1e-6:
        raise ValueError('Audio is too short or silent for synchronization')
    return envelope, first


def align_audio(a, b, max_lag_seconds=5):
    """Estimate t_b - t_a from normalized log-energy envelope correlation."""
    lags = correlation_lags(len(b), len(a))
    cross = correlate(b, a, method='fft')
    ones_a, ones_b = np.ones(len(a)), np.ones(len(b))
    denominator = np.sqrt(np.maximum(
        1e-12, correlate(b * b, ones_a, method='fft') *
        correlate(ones_b, a * a, method='fft')))
    overlap = correlate(ones_b, ones_a, method='fft')
    allowed = ((abs(lags) <= max_lag_seconds * ENVELOPE_HZ) &
               (overlap >= max(ENVELOPE_HZ, .5 * min(len(a), len(b)))))
    if not np.any(allowed):
        raise ValueError('Not enough overlapping audio within search range')
    scores = np.where(allowed, cross / denominator, -np.inf)
    best = int(np.argmax(scores))
    if scores[best] < .5:
        raise ValueError('Weak audio correlation; review synchronization manually')
    if abs(lags[best]) >= max_lag_seconds * ENVELOPE_HZ:
        raise ValueError('Audio optimum hits search boundary')
    return float(lags[best] / ENVELOPE_HZ), float(scores[best])


def probe(config, shifts):
    views = json.loads(Path(config).read_text())['views']
    if len(views) != 2:
        raise ValueError('Exactly two views required')
    cameras = [load_camera(v['calibration'], v.get('width', 1920),
                           v.get('height', 1080)) for v in views]
    detections = [json.loads(Path(v['detections']).read_text()) for v in views]
    (a, start_a), (b, start_b) = [audio_envelope(v['video']) for v in views]
    original_visual_offset = None
    results = []
    # Always establish the visual baseline before exercising an injected delay.
    for shift in dict.fromkeys([0., *shifts]):
        samples = round(shift * ENVELOPE_HZ)
        aa = np.pad(a, (max(0, -samples), 0))
        bb = np.pad(b, (max(0, samples), 0))
        coarse, correlation = align_audio(aa, bb)
        coarse += start_b - start_a
        shifted = [dict(r, timestamp_seconds=r['timestamp_seconds'] + shift)
                   for r in detections[1]]
        refined, sync = synchronize_ball(detections[0], shifted, cameras,
                                         initial=coarse)
        _, reconstruction = reconstruct_ball(detections[0], shifted, cameras,
                                              refined)
        if original_visual_offset is None:
            original_visual_offset = refined
        results.append(dict(
            injected_timestamp_shift_seconds=shift,
            coarse_audio_offset_seconds=coarse,
            audio_normalized_correlation=correlation,
            refined_visual_offset_seconds=refined,
            offset_change_error_ms=1000 * (refined - original_visual_offset - shift),
            ball_epipolar_cost_px=sync['cost_px'],
            valid_ball_frames=reconstruction['valid_frames'],
            total_frames=reconstruction['total_frames']))
    return dict(
        experimental=True, reference_labels_read=False,
        method='700–6000 Hz audio log-RMS envelope correlation at 200 Hz; '
               'then existing calibrated ball epipolar refinement',
        config=str(config), experiments=results,
        limitations=[
            'Not integrated into the upload UI or replay builder.',
            'Clock-shift experiments reuse existing recordings; they do not '
            'establish generalization to new cameras.',
            'Audio correlation is not a calibrated confidence; repeated sounds '
            'or edited soundtracks can give ambiguous matches.',
            'Acoustic travel time and audio/video recording latency mean audio '
            'alone is not accurate enough for ball triangulation.',
            'First 60 seconds only; no clock-drift or rolling-shutter correction.',
            'Requires supplied calibration and existing per-view ball detections.'])


def probe_audio_only(videos, max_seconds=120, max_lag_seconds=30):
    (a, start_a), (b, start_b) = [audio_envelope(v, max_seconds) for v in videos]
    offset, score = align_audio(a, b, max_lag_seconds)
    windows = []
    for start in range(0, int(min(len(a), len(b)) / ENVELOPE_HZ) - 19, 20):
        begin, end = start * ENVELOPE_HZ, (start + 20) * ENVELOPE_HZ
        try:
            lag, strength = align_audio(a[begin:end], b[begin:end], max_lag_seconds)
            windows.append(dict(start_seconds=start, end_seconds=start + 20,
                                offset_b_minus_a_seconds=lag + start_b - start_a,
                                normalized_correlation=strength))
        except ValueError as exc:
            windows.append(dict(start_seconds=start, end_seconds=start + 20,
                                rejected=True, reason=str(exc)))
    return dict(experimental=True, videos=[str(v) for v in videos],
                reference_labels_read=False, audio_only=True,
                visual_precision_verified=False,
                method='Audio log-RMS envelope normalized cross correlation; '
                       'no labels or camera calibration.',
                offset_b_minus_a_seconds=offset + start_b - start_a,
                normalized_correlation=score, envelope_hz=ENVELOPE_HZ,
                search_seconds=[-max_lag_seconds, max_lag_seconds],
                analyzed_audio_seconds=[len(a) / ENVELOPE_HZ, len(b) / ENVELOPE_HZ],
                windows=windows,
                limitations=['Audio travel time and recording latency affect '
                             'alignment; visual refinement is needed for 3D.',
                             'Correlation score is not a calibrated probability.',
                             'No clock-drift correction or ambiguous-peak test.',
                             'Not integrated into the upload UI.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--config')
    inputs.add_argument('--videos', nargs=2)
    parser.add_argument('--output', required=True)
    parser.add_argument('--shifts', type=float, nargs='*', default=[.5, 1., 2.])
    parser.add_argument('--audio-seconds', type=int, default=120)
    parser.add_argument('--max-lag-seconds', type=float, default=30)
    args = parser.parse_args()
    result = (probe(args.config, args.shifts) if args.config else
              probe_audio_only(args.videos, args.audio_seconds, args.max_lag_seconds))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result, indent=2, allow_nan=False))

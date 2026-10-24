"""Offline measurements from original phone frames. No point decisions live here."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import av
import cv2
import numpy as np
from scipy.signal import correlate, correlation_lags


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def inspect(path):
    with av.open(str(path)) as c:
        v = c.streams.video[0]
        return dict(
            file=Path(path).name,
            sha256=sha256(path),
            bytes=Path(path).stat().st_size,
            width=v.width,
            height=v.height,
            fps=float(v.average_rate),
            average_rate=str(v.average_rate),
            time_base=str(v.time_base),
            start_pts=v.start_time,
            duration_s=float(v.duration * v.time_base),
            frames=v.frames,
            audio=bool(c.streams.audio),
            codec=v.codec_context.name,
        )


def audio_signal(path, rate=8000):
    samples = []
    with av.open(str(path)) as c:
        if not c.streams.audio:
            return None
        start_s = float((c.streams.audio[0].start_time or 0) * c.streams.audio[0].time_base)
        res = av.AudioResampler(format="flt", layout="mono", rate=rate)
        for frame in c.decode(audio=0):
            for f in res.resample(frame):
                samples.append(f.to_ndarray().ravel())
        for f in res.resample(None):
            samples.append(f.to_ndarray().ravel())
    return np.r_[np.zeros(max(0, round(start_s * rate))), np.concatenate(samples)]


def audio_envelope(x):
    x = x[: len(x) // 8 * 8].reshape(-1, 8)
    return np.log1p(np.sqrt(np.mean(np.diff(x, axis=1) ** 2, axis=1)) * 200)


def estimate_sync(a, b):
    """b_time = a_time*drift + offset. Energy correlation is NOT exposure sync."""
    ea, eb = audio_envelope(a), audio_envelope(b)
    duration = min(len(ea), len(eb)) / 1000
    windows = []
    for t in np.linspace(5, max(5, duration - 20), 7):
        i, j = int(t * 1000), int((t + 12) * 1000)
        aa = ea[i:j]
        bb = eb[max(0, i - 10000) : min(len(eb), j + 10000)]
        aa = aa - aa.mean()
        bb = bb - bb.mean()
        cor = correlate(bb, aa, method="fft")
        lags = correlation_lags(len(bb), len(aa))
        offsets = (lags + max(0, i - 10000) - i) / 1000
        mask = (offsets >= -5) & (offsets <= 5)
        ids = np.where(mask)[0]
        best = ids[np.argmax(cor[mask])]
        k = int(lags[best])
        a0 = max(0, -k)
        b0 = max(0, k)
        n = min(len(aa) - a0, len(bb) - b0)
        coeff = (
            float(np.corrcoef(aa[a0 : a0 + n], bb[b0 : b0 + n])[0, 1])
            if n > 10 and aa[a0 : a0 + n].std() > 1e-9 and bb[b0 : b0 + n].std() > 1e-9
            else 0
        )
        windows.append(dict(t_s=float(t + 6), offset_s=float(offsets[best]), correlation=coeff))
    valid = [w for w in windows if w["correlation"] > 0.25]
    if len(valid) < 3:
        return dict(
            method="audio correlation failed; manual offset required",
            offset_s=0,
            drift=1,
            verified=False,
            uncertainty_s=None,
            windows=windows,
        )
    offsets = np.array([w["offset_s"] for w in valid])
    med = float(np.median(offsets))
    residual = float(np.percentile(np.abs(offsets - med), 90))
    # Do not overfit acoustic/reflection differences to clock drift.
    return dict(
        method="7-window shared-audio energy correlation; visual verification pending",
        offset_s=med,
        drift=1.0,
        verified=False,
        uncertainty_s=max(1 / 60, residual + 0.01),
        windows=windows,
        sound_travel_note="Acoustic delay depends on contact position; rolling shutter and exposure are unverified.",
        drift_note="No stable drift established; unity clock rate retained. Manual offset supported.",
    )


class OrangeTracker:
    """Conservative CPU orange color/motion baseline; no predicted positions.

    Narrow color thresholds deliberately return missing on weak blurred balls.
    The broader skin-like color experiment failed labeled evaluation and is not
    shipped. Heuristic scores are never probabilities of a correct ruling.
    """

    def __init__(self):
        self.previous = None
        self.last = None
        self.velocity = np.zeros(2)
        self.gap = 100

    def update(self, image, t):
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([4, 135, 135], np.uint8), np.array([28, 255, 255], np.uint8))
        mask[: int(h * 0.22)] = 0
        n, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray, self.previous) if self.previous is not None else np.zeros_like(gray)
        candidates = []
        for k in range(1, n):
            x, y, bw, bh, area = stats[k]
            cx, cy = centers[k]
            if not 2 <= area <= 110 or max(bw, bh) > 35 or min(bw, bh) < 1:
                continue
            saturation = float(hsv[y : y + bh, x : x + bw, 1][labels[y : y + bh, x : x + bw] == k].mean()) / 255
            motion = float(diff[y : y + bh, x : x + bw].max()) / 255
            compact = area / max(1, bw * bh)
            value = 0.35 * saturation + 0.45 * min(1, motion * 3) + 0.2 * compact
            if self.last is not None and self.gap < 9:
                dt = t - self.last[2]
                pred = np.array(self.last[:2]) + self.velocity * dt
                distance = np.linalg.norm(np.array([cx, cy]) - pred)
                value += 0.15 * math.exp(-distance / 90)
            candidates.append(
                dict(x=float(cx), y=float(cy), score=float(min(0.99, value)), area_px=int(area), motion=motion)
            )
        best = max(candidates, key=lambda c: c["score"]) if candidates else None
        if best and (best["motion"] < 0.025 or best["score"] < 0.52):
            best = None
        if best:
            if self.last is not None and self.gap < 9:
                dt = t - self.last[2]
                if dt > 0:
                    self.velocity = 0.5 * self.velocity + 0.5 * (np.array([best["x"], best["y"]]) - self.last[:2]) / dt
            self.last = (best["x"], best["y"], t)
            self.gap = 0
        else:
            self.gap += 1
        self.previous = gray
        return best, candidates


def track_clip(path, output, max_frames=None, width=1280):
    """Decode ALL original PTS, resize for CPU baseline, keep source pixel coordinates."""
    tracker = OrangeTracker()
    rows = []
    latencies = []
    start = time.perf_counter()
    decode_s = 0
    with av.open(str(path)) as c:
        stream = c.streams.video[0]
        stream.thread_type = "AUTO"
        frames = c.decode(video=0)
        while max_frames is None or len(rows) < max_frames:
            tick = time.perf_counter()
            try:
                f = next(frames)
            except StopIteration:
                break
            im = f.reformat(width=width, height=round(f.height * width / f.width), format="bgr24").to_ndarray()
            decode_s += time.perf_counter() - tick
            if f.pts is None:
                raise ValueError("Missing source PTS; refusing fabricated source time")
            t = float(f.pts * f.time_base)
            tick = time.perf_counter()
            point, candidates = tracker.update(im, t)
            latencies.append(time.perf_counter() - tick)
            scale = f.width / width
            row = dict(
                seq=len(rows),
                pts=int(f.pts),
                time_base=str(f.time_base),
                t_source_s=t,
                t_game_s=t,
                source_size=[f.width, f.height],
                x=None,
                y=None,
                score=None,
                status="missing",
                candidates=len(candidates),
            )
            if point:
                row.update(x=point["x"] * scale, y=point["y"] * scale, score=point["score"], status="observed_2d")
            rows.append(row)
            if len(rows) % 900 == 0:
                print(f"{Path(path).name}: {len(rows)} source frames", flush=True)
    elapsed = time.perf_counter() - start
    report = dict(
        detector="classical-orange-color-motion",
        source_sha256=sha256(path),
        device="CPU",
        input_width=width,
        source_frames=len(rows),
        observed_frames=sum(r["x"] is not None for r in rows),
        elapsed_s=elapsed,
        end_to_end_fps=len(rows) / elapsed,
        decode_s=decode_s,
        detection_s=sum(latencies),
        latency_p50_ms=float(np.median(latencies) * 1000),
        latency_p95_ms=float(np.percentile(latencies, 95) * 1000),
        recall=None,
        false_positives=None,
        accuracy_note="Coverage is not recall. Separate human labels required.",
        score_note="Heuristic ranking score; not a probability of correct detection or ruling.",
    )
    Path(output).write_text(json.dumps(dict(frames=rows, report=report), allow_nan=False))
    return rows, report


def rally_candidates(rows, envelope=None):
    """Candidate action intervals only; ball disappearance NEVER assigns a winner."""
    valid = [r for r in rows if r["x"] is not None]
    if not valid:
        return []
    runs = []
    run = []
    for r in valid:
        if run and r["t_game_s"] - run[-1]["t_game_s"] > 0.8:
            if run[-1]["t_game_s"] - run[0]["t_game_s"] > 0.6:
                runs.append(run)
            run = []
        run.append(r)
    if run and run[-1]["t_game_s"] - run[0]["t_game_s"] > 0.6:
        runs.append(run)
    points = []
    for run in runs:
        start, end = run[0]["t_game_s"], run[-1]["t_game_s"]
        # Avoid a full-minute noisy run becoming one unhelpful selectable point.
        # Long stretches stay explicitly candidate intervals, not asserted rallies.
        for a in np.arange(start, end, 12):
            b = min(end, a + 12)
            if b - a < 0.4:
                continue
            points.append(
                dict(
                    id=f"r{len(points) + 1:03}",
                    start_s=float(a),
                    end_s=float(b),
                    evidence_s=float(b),
                    status="unresolved",
                    winner=None,
                    kind="candidate_rally",
                    reason=(
                        "Ball observations define a candidate activity interval; terminal "
                        "contact and winner need review."
                    ),
                    boundary_uncertainty_s=0.8,
                    evidence_origin="detector_candidate",
                    rule_ref="2.5, 2.7, 2.9–2.10",
                )
            )
    return points


def measure_toss(samples, release_s, apex_s, contact_s=None, sigma_m=0, calibrated=False):
    """Endpoint chord on upward release→apex only; implementation convention.

    Returns unavailable instead of pretending an absent release is a wrist point.
    samples contain real/synthetic metric positions with their own provenance.
    """
    if not calibrated:
        return dict(status="unavailable", reason="Metric calibration unverified")
    if sigma_m < 0 or not math.isfinite(sigma_m):
        raise ValueError("Invalid position uncertainty")
    if release_s >= apex_s:
        raise ValueError("Release must precede apex")

    def get(t):
        matches = [r for r in samples if abs(r["t_s"] - t) < 1e-6 and r.get("pos_m") is not None]
        return np.array(matches[0]["pos_m"], float) if matches else None

    release, apex = get(release_s), get(apex_s)
    if release is None or apex is None:
        return dict(status="unavailable", reason="Missing observed release or apex")
    delta = apex - release
    if not np.isfinite(delta).all() or delta[2] <= 0:
        return dict(status="unavailable", reason="No observed positive upward toss")
    angle = math.degrees(math.atan2(float(np.linalg.norm(delta[:2])), delta[2]))
    sigma_height = math.sqrt(2) * sigma_m
    return dict(
        status="measured",
        height_m=float(delta[2]),
        height_interval_m=[float(delta[2] - 2 * sigma_height), float(delta[2] + 2 * sigma_height)],
        rise_angle_deg=angle,
        angle_estimator="release-to-apex chord; implementation convention, not official TTR definition",
        release_s=release_s,
        apex_s=apex_s,
        contact_s=contact_s,
        sigma_height_m=sigma_height,
        fall_segment_used_for_angle=False,
        full_service_legality="unverified",
    )

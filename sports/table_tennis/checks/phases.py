"""phases: where play starts and stops, from the ball alone.

A rally starts at the serve *release*: the ball has stayed within `still_radius_m` of one spot in a serve zone (at
or behind an end line, at hand height) for `still_s`, then rises faster than `toss_vz_m_s` and keeps rising on the
next sample. It ends at the first of: a floor bounce (z within `floor_band_m` of the floor), no confident sample for
`gap_s`, or the ball held still again for `end_still_s`. Between rallies the phase is `between_points`. The judge's
voice ("point", "let") always overrides this.

verdict: {"segments": [{rally_no, t_start_s, t_end_s|None, server_side, end_reason|None}], "phase": str}
"""

from __future__ import annotations

import math

from trophy_engine.checks.api import Field, Track, merge_params, result

PARAMS = {
    "min_conf": 0.3,
    "still_radius_m": 0.08,  # the ball stays within this of one spot while held
    "release_slack_s": 0.15,  # the toss may begin this long after the ball last looked still
    "still_s": 0.25,  # how long it must be still before a toss counts as a serve
    "toss_vz_m_s": 0.3,  # the first step after the release rises at least this fast
    "toss_rise_m": [0.02, 0.035, 0.045],  # and the ball is this much above where it was held, 1, 2 and 3 samples on
    #   (a 7 cm toss leaves the hand at 1.2 m/s and is 3.3 / 5.6 / 6.8 cm up after 33 / 67 / 100 ms)
    "toss_xy_m": 0.2,  # a toss goes up, not sideways: horizontal travel over those samples stays under this
    "serve_zone_behind_m": 0.9,  # |x| >= half length - this: at or behind the end line
    "serve_zone_z_m": [-0.3, 0.8],  # hand height band relative to the surface
    "gap_s": 1.0,  # no ball for this long -> rally over (lost)
    "floor_band_m": 0.12,  # z within this of the floor -> floor bounce, rally over
    "end_still_s": 0.5,  # ball held still this long during a rally -> over (stopped)
    "min_rally_s": 0.3,  # a rally shorter than this before 'stopped' is ignored
    "min_false_start_s": 0.6,  # a 'stopped' segment shorter than this never left the hand: dropped
}


def _dist(a, b) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def check(track: Track, field: Field, params=None, t0=None, t1=None, **q):
    p = merge_params(PARAMS, params)
    tr = track.window(t0, t1).good(p["min_conf"])
    s = tr.samples
    z_lo, z_hi = p["serve_zone_z_m"]
    segments = []
    phase = "idle"
    anchor = None  # the still spot (sample) and when stillness began
    still_since = None
    last_still = None  # the last sample at which the ball had been still for still_s (the release candidate)
    still_z = None  # mean height while held (the release height)
    still_n = 0
    cur = None
    rally_no = 0

    def in_zone(smp) -> bool:
        return field.in_serve_zone(smp.x, smp.z, p["serve_zone_behind_m"], z_lo, z_hi)

    def update_still(i: int) -> bool:
        """Track whether the ball is being held; returns True when it has been still for still_s."""
        nonlocal anchor, still_since, last_still, still_z, still_n
        smp = s[i]
        if anchor is not None and _dist(anchor, smp) <= p["still_radius_m"] and smp.t - s[i - 1].t <= Track.MAX_STEP_S:
            if still_z is None:
                still_z, still_n = anchor.z, 1
            still_z, still_n = (still_z * still_n + smp.z) / (still_n + 1), still_n + 1
            if smp.t - still_since >= p["still_s"]:
                last_still = smp
                return True
            return False
        anchor, still_since, still_z, still_n = smp, smp.t, smp.z, 1
        return False

    for i, smp in enumerate(s):
        if i == 0:
            anchor, still_since, still_z, still_n = smp, smp.t, smp.z, 1
            continue
        if cur is None:
            was_still = last_still is not None and 0.0 <= s[i - 1].t - last_still.t <= p["release_slack_s"]
            vz = tr.step_velocity(i)[2]
            z0 = still_z if (was_still and still_z is not None) else s[i - 1].z
            rising = (
                i + 2 < len(s)
                and tr.contiguous(i - 1, i + 2)
                and all(s[i + k].z - z0 >= p["toss_rise_m"][k] for k in range(3))
                and math.hypot(s[i + 2].x - s[i - 1].x, s[i + 2].y - s[i - 1].y) <= p["toss_xy_m"]
            )
            if was_still and in_zone(last_still) and vz >= p["toss_vz_m_s"] and rising:
                rally_no += 1
                cur = {
                    "rally_no": rally_no,
                    "t_start_s": last_still.t,
                    "t_end_s": None,
                    "server_side": field.side(last_still.x),
                    "end_reason": None,
                }
                segments.append(cur)
                phase = "rally"
                anchor, still_since, last_still, still_z, still_n = None, None, None, None, 0
                continue
            update_still(i)
            phase = "between_points" if segments else "idle"
            continue
        # inside a rally
        if smp.z <= field.floor_z_m + p["floor_band_m"]:
            cur["t_end_s"], cur["end_reason"] = smp.t, "floor"
            cur, phase = None, "between_points"
            anchor, still_since, last_still, still_z, still_n = smp, smp.t, None, smp.z, 1
            continue
        if smp.t - s[i - 1].t >= p["gap_s"]:
            cur["t_end_s"], cur["end_reason"] = s[i - 1].t, "lost"  # over when the ball was last seen
            cur, phase = None, "between_points"
            anchor, still_since, last_still, still_z, still_n = smp, smp.t, None, smp.z, 1
            continue
        if update_still(i) and smp.t - cur["t_start_s"] > p["min_rally_s"] and smp.t - still_since >= p["end_still_s"]:
            cur["t_end_s"], cur["end_reason"] = still_since, "stopped"
            cur, phase = None, "between_points"
            # the ball may already be held for the next serve: keep the anchor
    if cur is not None and s and t1 is not None and t1 - s[-1].t >= p["gap_s"]:
        cur["t_end_s"], cur["end_reason"] = s[-1].t, "lost"
        phase = "between_points"
    # a 'rally' that stopped almost at once with the ball still in hand was a twitch, not a serve
    segments = [
        g
        for g in segments
        if not (g["end_reason"] == "stopped" and g["t_end_s"] - g["t_start_s"] < p["min_false_start_s"])
    ]
    for k, g in enumerate(segments, 1):
        g["rally_no"] = k
    ev = {"n_rallies": len(segments), "samples": len(s)}
    text = f"{len(segments)} rallies found; phase now {phase}"
    return result("phases", {"segments": segments, "phase": phase}, t_s=s[-1].t if s else None, evidence=ev, text=text)

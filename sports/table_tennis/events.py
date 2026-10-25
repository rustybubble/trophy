"""Table tennis: layer-1 observations -> layer-2 events (bounce, net, ball_dead).

Handwritten golden reference for the Droid. Pure, deterministic, stdlib only (see the import allowlist in
trophy_engine.sportmod.loader). It emits measurements with uncertainty; it never decides a point (D-18).

How a bounce is found
  1. Per camera, keep ball samples with conf >= capture.min_conf and a pixel position.
  2. A bounce candidate is a local maximum of image y (the lowest point on screen) with the ball moving down
     (dy/dt > min_vy_px_s) over the previous `min_track_len` samples and up afterwards. The apex time and pixel are
     refined with a parabola through the three samples around the maximum.
  3. The apex pixel is mapped through the camera's homography (px -> metres on the play plane; exact at the bounce
     because the ball is on the plane). Inside the table + plane_margin_m -> surface "table", else "floor".
  4. Candidates from different cameras within merge_window_s are the same bounce: positions are fused by inverse
     variance (sigma grows with the camera's reprojection error; untrusted cameras count double).
  5. Signed distances to the four lines give p_in = Phi(d_min / sigma). Within edge_band_m of a line the edge
     probabilities are reported: top_edge / side_face / surface sum to 1 (a heuristic from d and sigma; the engine's
     `check: ensemble` lets AI voters refine a challenged edge call).
A racket hit looks like a bounce (a local minimum in height) but the ball reverses along x there, so it is emitted as
`contact` instead. A net is an x-reversal within net.window_m of the net plane with no bounce in between (side-on
cameras map x well even when the ball is above the plane). ball_dead follows a floor bounce or dead.gap_s of silence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from trophy_engine.sportmod.api import (
    BallSample,
    Camera,
    ModuleState,
    Observation,
    ball_dead_event,
    bounce_event,
    contact_event,
    fuse,
    net_event,
    phi,
    rect_line_distances,
    side_of,
)


@dataclass
class Candidate:
    t_s: float
    cam_id: str
    x: float
    y: float
    sigma: float
    conf: float
    surface: str  # the play surface ("table"/"court") | "floor" | "contact" (a racket hit: the ball reversed along x)


def _parabola_vertex(t0: float, y0: float, t1: float, y1: float, t2: float, y2: float) -> tuple[float, float]:
    """Vertex of the parabola through three points (falls back to the middle point when degenerate)."""
    d = (t0 - t1) * (t0 - t2) * (t1 - t2)
    if abs(d) < 1e-9:
        return t1, y1
    a = (t2 * (y1 - y0) + t1 * (y0 - y2) + t0 * (y2 - y1)) / d
    b = (t2 * t2 * (y0 - y1) + t1 * t1 * (y2 - y0) + t0 * t0 * (y1 - y2)) / d
    if abs(a) < 1e-9:
        return t1, y1
    tv = -b / (2 * a)
    if not (min(t0, t2) <= tv <= max(t0, t2)):
        return t1, y1
    c = y1 - a * t1 * t1 - b * t1
    return tv, a * tv * tv + b * tv + c


def _candidates(cam: Camera, samples: list[BallSample], state: ModuleState) -> list[Candidate]:
    cfg = state.config
    b = cfg["bounce"]
    k = int(b["min_track_len"])
    min_vy = float(b["min_vy_px_s"])
    half_l = float(cfg["court"]["length_m"]) / 2 + float(b["plane_margin_m"])
    half_w = float(cfg["court"]["width_m"]) / 2 + float(b["plane_margin_m"])
    sigma = float(b["sigma_m"]) * (1.0 + cam.reproj_err_px / 5.0) * (1.0 if cam.trusted else 2.0)
    play_surface = str(cfg["court"].get("surface", "table"))

    pts = [s for s in samples if s.px is not None and s.conf >= float(cfg["capture"]["min_conf"])]
    pts.sort(key=lambda s: (s.t_s, s.seq))
    out: list[Candidate] = []
    for i in range(k, len(pts) - k):
        v = pts[i].px[1]  # type: ignore[index]
        before = pts[i - k]
        after = pts[i + k]
        if any(pts[j].px[1] > v for j in range(i - k, i + k + 1) if j != i):  # type: ignore[index]
            continue
        dt_b = pts[i].t_s - before.t_s
        dt_a = after.t_s - pts[i].t_s
        if dt_b <= 0 or dt_a <= 0:
            continue
        vy_before = (v - before.px[1]) / dt_b  # type: ignore[index]
        vy_after = (after.px[1] - v) / dt_a  # type: ignore[index]
        if vy_before < min_vy or vy_after > -min_vy:
            continue
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        tv, yv = _parabola_vertex(p0.t_s, p0.px[1], p1.t_s, p1.px[1], p2.t_s, p2.px[1])  # type: ignore[index]
        # x at the vertex: linear interpolation between the neighbours
        if p2.t_s > p0.t_s:
            frac = (tv - p0.t_s) / (p2.t_s - p0.t_s)
            u = p0.px[0] + frac * (p2.px[0] - p0.px[0])  # type: ignore[index]
        else:
            u = p1.px[0]  # type: ignore[index]
        x, y = cam.to_field(u, yv)
        # A racket hit is also a local minimum in height, but the ball reverses its travel along x there; a bounce
        # keeps going. Side-on cameras map x faithfully even when the ball is above the plane.
        j0, j1 = max(0, i - k - 1), min(len(pts) - 1, i + k + 1)
        x_in0 = cam.to_field(pts[j0].px[0], pts[j0].px[1])[0]  # type: ignore[index]
        x_in1 = cam.to_field(pts[i - 1].px[0], pts[i - 1].px[1])[0]  # type: ignore[index]
        x_out0 = cam.to_field(pts[i + 1].px[0], pts[i + 1].px[1])[0]  # type: ignore[index]
        x_out1 = cam.to_field(pts[j1].px[0], pts[j1].px[1])[0]  # type: ignore[index]
        dx_in, dx_out = x_in1 - x_in0, x_out1 - x_out0  # travel direction before and after the flip
        reversed_x = dx_in * dx_out < 0 and abs(dx_in) > 0.02 and abs(dx_out) > 0.02
        on_table = abs(x) <= half_l and abs(y) <= half_w
        conf = min(p0.conf, p1.conf, p2.conf)
        surface = "contact" if reversed_x else (play_surface if on_table else "floor")
        out.append(Candidate(t_s=tv, cam_id=cam.cam_id, x=x, y=y, sigma=sigma, conf=conf, surface=surface))
    return out


def _merge(cands: list[Candidate], window_s: float) -> list[list[Candidate]]:
    cands = sorted(cands, key=lambda c: c.t_s)
    groups: list[list[Candidate]] = []
    for c in cands:
        if groups and c.t_s - groups[-1][0].t_s <= window_s and all(g.cam_id != c.cam_id for g in groups[-1]):
            groups[-1].append(c)
        else:
            groups.append([c])
    return groups


def _edge_probs(d_edge: float, sigma: float, band: float) -> dict[str, float] | None:
    if abs(d_edge) >= band:
        return None
    p_in = phi(d_edge / sigma)
    w_edge = 1.0 - abs(d_edge) / band  # closer to the line -> more likely the top edge took the hit
    top = p_in * w_edge
    surface = p_in * (1.0 - w_edge)
    side = 1.0 - p_in
    return {"top_edge": top, "side_face": side, "surface": surface}


def events(observations: Iterable[Observation], state: ModuleState) -> Iterable[dict]:
    cfg = state.config
    play_surface = str(cfg["court"].get("surface", "table"))
    cams: dict[str, Camera] = {}
    samples: dict[str, list[BallSample]] = {}
    for ob in observations:
        if isinstance(ob, Camera):
            cams[ob.cam_id] = ob
        elif isinstance(ob, BallSample):
            samples.setdefault(ob.cam_id, []).append(ob)

    length = float(cfg["court"]["length_m"])
    width = float(cfg["court"]["width_m"])
    net_x = float(cfg["court"]["net_x_m"])
    band = float(cfg["bounce"]["edge_band_m"])

    cands: list[Candidate] = []
    for cam_id, cam in cams.items():
        cands += _candidates(cam, samples.get(cam_id, []), state)

    out: list[dict] = []
    bounces: list[tuple[float, str, str]] = []  # (t, side, surface)
    window = float(cfg["bounce"]["merge_window_s"])
    for group in _merge([c for c in cands if c.surface == "contact"], window):
        t = sum(c.t_s for c in group) / len(group)
        x = sum(c.x for c in group) / len(group)
        conf = 1.0 - _prod(1.0 - c.conf for c in group)
        out.append(
            contact_event(
                state, t_s=t, cams=sorted(c.cam_id for c in group), side=side_of(x, net_x), kind="racket", conf=conf
            )
        )
    for group in _merge([c for c in cands if c.surface != "contact"], window):
        t = sum(c.t_s for c in group) / len(group)
        x, sx = fuse((c.x, c.sigma) for c in group)
        y, sy = fuse((c.y, c.sigma) for c in group)
        sigma = max(sx, sy)
        conf = 1.0 - _prod(1.0 - c.conf for c in group)
        surface = play_surface if sum(1 for c in group if c.surface != "floor") * 2 >= len(group) else "floor"
        d = rect_line_distances(x, y, length, width)
        d_min = min(d.values())
        p_in = phi(d_min / sigma)
        edge = _edge_probs(d_min, sigma, band) if surface == play_surface else None
        side = side_of(x, net_x)
        out.append(
            bounce_event(
                state,
                t_s=t,
                cams=sorted(c.cam_id for c in group),
                surface=surface,
                side=side,
                x=x,
                y=y,
                sigma_m=sigma,
                d_lines_m=d,
                p_in=p_in,
                edge=edge,
                conf=conf,
            )
        )
        bounces.append((t, side, surface))

    # Net: x-reversal near the net plane between consecutive bounces on the same side (no bounce in between).
    net_window = float((cfg.get("net") or {}).get("window_m", 0.0))
    if net_window > 0 and cams:
        for cam_id, cam in cams.items():
            pts = sorted((s for s in samples.get(cam_id, []) if s.px is not None), key=lambda s: s.t_s)
            xs = [(s.t_s, cam.to_field(s.px[0], s.px[1])[0]) for s in pts]  # type: ignore[index]
            for i in range(1, len(xs) - 1):
                t_prev, x_prev = xs[i - 1]
                t_i, x_i = xs[i]
                t_next, x_next = xs[i + 1]
                toward = (x_i - x_prev) * (x_next - x_i)
                if toward < 0 and abs(x_i - net_x) <= net_window and _no_bounce_between(bounces, t_prev, t_next):
                    from_side = side_of(x_prev, net_x)
                    out.append(net_event(state, t_s=t_i, cams=[cam_id], kind="into", from_side=from_side, conf=0.6))
                    break  # one net per log is enough for a rally; the engine ends the rally there

    # Ball dead: after a floor bounce, or after dead.gap_s of silence at the end of the log.
    all_samples = sorted((s for ss in samples.values() for s in ss if s.px is not None), key=lambda s: s.t_s)
    if all_samples:
        last_t = all_samples[-1].t_s
        last_side = bounces[-1][1] if bounces else None
        gap = float(cfg["dead"]["gap_s"])
        floor = [b for b in bounces if b[2] == "floor"]
        if floor:
            t_floor, floor_side = floor[0][0], floor[0][1]
            out.append(
                ball_dead_event(
                    state, t_s=t_floor + 0.05, cams=sorted(cams), reason="floor", last_side=floor_side, conf=0.9
                )
            )
        else:
            out.append(
                ball_dead_event(
                    state, t_s=last_t + gap, cams=sorted(cams), reason="lost", last_side=last_side, conf=0.7
                )
            )

    out.sort(key=lambda e: (e["t_game_s"], e["type"]))
    return out


def _no_bounce_between(bounces: list[tuple[float, str, str]], t0: float, t1: float) -> bool:
    return not any(t0 <= t <= t1 for t, _s, _f in bounces)


def _prod(values: Iterable[float]) -> float:
    p = 1.0
    for v in values:
        p *= v
    return p

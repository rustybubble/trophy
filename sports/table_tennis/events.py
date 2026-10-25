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

from trophy_engine.sportmod.api import (
    BallSample,
    Camera,
    Iterable,
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


class Candidate:
    """A bounce / hit candidate from one camera. A plain class: module code may not import dataclasses (D-35)."""

    def __init__(
        self,
        *,
        t_s: float,
        cam_id: str,
        x: float,
        y: float,
        sigma: float,  # isotropic floor (config bounce.sigma_m, scaled by reprojection error and trust)
        conf: float,
        surface: str,  # the play surface ("table"/"court") | "floor" | "contact" (a racket hit: reversed along x)
        sigma_x: float = 0.0,  # 1-sigma along the table (m): the floor, plus PX_SIGMA through the homography
        sigma_y: float = 0.0,  # 1-sigma across the table: large from a camera near table height
    ) -> None:
        self.t_s, self.cam_id, self.x, self.y = t_s, cam_id, x, y
        self.sigma, self.conf, self.surface = sigma, conf, surface
        self.sigma_x, self.sigma_y = sigma_x, sigma_y


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
        # A racket hit is also a local minimum in height, but the ball reverses its travel along the table there; a
        # bounce keeps going. The travel is measured IN THE IMAGE along the table's long axis at the vertex (the image
        # direction of field +x there), never by projecting airborne samples through the plane homography: from a
        # camera near table height a ball above the table maps far away or behind the camera, which fakes a reversal.
        ax = _image_axis(cam, x, y)
        j0, j1 = max(0, i - k - 1), min(len(pts) - 1, i + k + 1)
        dx_in = _along(pts[j0], pts[i - 1], ax)
        dx_out = _along(pts[i + 1], pts[j1], ax)
        min_px = 0.02 * ax[2]  # 2 cm of travel along the table, in pixels at this point
        reversed_x = dx_in * dx_out < 0 and abs(dx_in) > min_px and abs(dx_out) > min_px
        on_table = abs(x) <= half_l and abs(y) <= half_w
        conf = min(p0.conf, p1.conf, p2.conf)
        surface = "contact" if reversed_x else (play_surface if on_table else "floor")
        if surface == "floor" and not _below_table_edge(
            cam, u, yv, float(cfg["court"]["length_m"]), float(cfg["court"]["width_m"])
        ):
            # Off the table but above its near edge in the image: the ball is in the air (a lob's top, a hit), not on
            # the floor. The plane homography maps such a point far away; it is not a bounce at all.
            continue
        if reversed_x:  # a hit is in the air: its side comes from the image (which side of the net), not the plane
            net_x = float(cfg["court"]["net_x_m"])
            nu, nv = _to_image(_inv3(cam.H_img_to_field), net_x, 0.0)
            nax = _image_axis(cam, net_x, 0.0)
            x = net_x + ((u - nu) * nax[0] + (yv - nv) * nax[1]) / nax[2]
        sx, sy = _plane_sigma(cam, u, yv, sigma)
        out.append(
            Candidate(
                t_s=tv, cam_id=cam.cam_id, x=x, y=y, sigma=sigma, conf=conf, surface=surface, sigma_x=sx, sigma_y=sy
            )
        )
    return out


def _inv3(h: tuple[float, ...]) -> tuple[float, ...]:
    a, b, c, d, e, f, g, hh, i = h
    det = a * (e * i - f * hh) - b * (d * i - f * g) + c * (d * hh - e * g)
    if abs(det) < 1e-15:
        return h
    return (
        (e * i - f * hh) / det, (c * hh - b * i) / det, (b * f - c * e) / det,
        (f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det,
        (d * hh - e * g) / det, (b * g - a * hh) / det, (a * e - b * d) / det,
    )  # fmt: skip


def _to_image(h_inv: tuple[float, ...], x: float, y: float) -> tuple[float, float]:
    w = h_inv[6] * x + h_inv[7] * y + h_inv[8]
    w = w if abs(w) > 1e-12 else 1e-12
    return ((h_inv[0] * x + h_inv[1] * y + h_inv[2]) / w, (h_inv[3] * x + h_inv[4] * y + h_inv[5]) / w)


def _image_axis(cam: Camera, x: float, y: float) -> tuple[float, float, float]:
    """Unit image direction of field +x at (x, y) on the play plane, and pixels per metre along it."""
    h_inv = _inv3(cam.H_img_to_field)
    u0, v0 = _to_image(h_inv, x, y)
    u1, v1 = _to_image(h_inv, x + 0.1, y)
    n = ((u1 - u0) ** 2 + (v1 - v0) ** 2) ** 0.5
    if n < 1e-9:
        return 1.0, 0.0, 1.0
    return (u1 - u0) / n, (v1 - v0) / n, n / 0.1


PX_SIGMA = 2.0  # 1-sigma of a detector's bounce pixel (BlurBall's median error is about 1 px; parabola refinement)
EDGE_MAX_SIGMA_M = 0.06  # an edge (top edge vs side face) is only judged when the position is this precise


def _plane_sigma(cam: Camera, u: float, v: float, floor: float) -> tuple[float, float]:
    """1-sigma of the plane position along x and y: PX_SIGMA pixels through the homography's local Jacobian, plus the
    isotropic floor. From a camera near table height the across-table term dominates."""
    x0, y0 = cam.to_field(u, v)
    xu, yu = cam.to_field(u + 1.0, v)
    xv, yv = cam.to_field(u, v + 1.0)
    jx = ((xu - x0) ** 2 + (xv - x0) ** 2) ** 0.5 * PX_SIGMA
    jy = ((yu - y0) ** 2 + (yv - y0) ** 2) ** 0.5 * PX_SIGMA
    return (floor**2 + jx**2) ** 0.5, (floor**2 + jy**2) ** 0.5


def _below_table_edge(cam: Camera, u: float, v: float, length: float, width: float) -> bool:
    """True when image point (u, v) is below the table's lower long edge on screen (where a floor bounce must be, for
    a camera above the floor). Past the table's ends there is no edge to compare with, so it counts as below."""
    h_inv = _inv3(cam.H_img_to_field)
    best = None
    for y_edge in (-width / 2, width / 2):
        a = _to_image(h_inv, -length / 2, y_edge)
        b = _to_image(h_inv, length / 2, y_edge)
        lo, hi = (a, b) if a[0] <= b[0] else (b, a)
        if not lo[0] <= u <= hi[0] or hi[0] - lo[0] < 1e-6:
            continue
        v_edge = lo[1] + (u - lo[0]) / (hi[0] - lo[0]) * (hi[1] - lo[1])
        best = v_edge if best is None else max(best, v_edge)
    return best is None or v > best


def _along(a: BallSample, b: BallSample, ax: tuple[float, float, float]) -> float:
    """Image displacement a -> b projected on the table's long axis (pixels; the sign is the direction)."""
    return (b.px[0] - a.px[0]) * ax[0] + (b.px[1] - a.px[1]) * ax[1]  # type: ignore[index]


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
        x, sx = fuse((c.x, c.sigma_x or c.sigma) for c in group)
        y, sy = fuse((c.y, c.sigma_y or c.sigma) for c in group)
        conf = 1.0 - _prod(1.0 - c.conf for c in group)
        surface = play_surface if sum(1 for c in group if c.surface != "floor") * 2 >= len(group) else "floor"
        d = rect_line_distances(x, y, length, width)
        nearest = min(d, key=lambda k: d[k])
        d_min = d[nearest]
        sigma = sx if nearest.startswith("end") else sy  # the uncertainty that matters for that line
        p_in = phi(d_min / sigma)
        precise = sigma <= EDGE_MAX_SIGMA_M
        edge = _edge_probs(d_min, sigma, band) if surface == play_surface and precise else None
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
            # signed metres from the net along the table, measured in the image (an airborne ball through the plane
            # homography lands anywhere from a camera near table height)
            h_inv = _inv3(cam.H_img_to_field)
            nu, nv = _to_image(h_inv, net_x, 0.0)
            nax = _image_axis(cam, net_x, 0.0)
            xs = [
                (s.t_s, net_x + ((s.px[0] - nu) * nax[0] + (s.px[1] - nv) * nax[1]) / nax[2])  # type: ignore[index]
                for s in pts
            ]
            for i in range(1, len(xs) - 1):
                t_prev, x_prev = xs[i - 1]
                t_i, x_i = xs[i]
                t_next, x_next = xs[i + 1]
                toward = (x_i - x_prev) * (x_next - x_i)
                if toward < 0 and abs(x_i - net_x) <= net_window and _no_bounce_between(bounces, t_prev, t_next):
                    from_side = side_of(x_prev, net_x)
                    out.append(net_event(state, t_s=t_i, cams=[cam_id], kind="into", from_side=from_side, conf=0.6))
                    break  # one net per log is enough for a rally; the engine ends the rally there

    # Ball dead: after each floor bounce, and after dead.gap_s with no *tracked* ball. A ball in play is a run of
    # >= dead.min_run consecutive detections (seq gap <= dead.max_seq_gap) that move <= dead.max_jump_px between
    # frames; isolated detections between rallies (hands, shirts, the ball being carried) never keep a rally alive.
    dcfg = cfg["dead"]
    gap = float(dcfg["gap_s"])
    tracked = _tracked_times(
        samples, int(dcfg.get("min_run", 1)), float(dcfg.get("max_jump_px", 0.0)), int(dcfg.get("max_seq_gap", 2))
    )
    deads: list[tuple[float, str, str | None, float]] = []  # (t, reason, last_side, conf)
    for t_floor, floor_side, _surface in (b for b in bounces if b[2] == "floor"):
        deads.append((t_floor + 0.05, "floor", floor_side, 0.9))
    for t_gap in _gaps(tracked, gap):
        deads.append((t_gap, "lost", _side_before(bounces, t_gap), 0.7))
    deads.sort(key=lambda d: d[0])
    last_dead = None
    for t_dead, reason, side, conf in deads:
        if last_dead is not None and t_dead - last_dead < 1.0:
            continue  # one dead ball per stretch of dead time
        out.append(ball_dead_event(state, t_s=t_dead, cams=sorted(cams), reason=reason, last_side=side, conf=conf))
        last_dead = t_dead

    out.sort(key=lambda e: (e["t_game_s"], e["type"]))
    return out


def _no_bounce_between(bounces: list[tuple[float, str, str]], t0: float, t1: float) -> bool:
    return not any(t0 <= t <= t1 for t, _s, _f in bounces)


def _prod(values: Iterable[float]) -> float:
    p = 1.0
    for v in values:
        p *= v
    return p


def _tracked_times(samples: dict[str, list[BallSample]], min_run: int, max_jump_px: float, max_seq_gap: int) -> list[float]:
    """Game times at which some camera had the ball *tracked*: inside a run of >= min_run consecutive detections
    (seq gap <= max_seq_gap) whose pixel jump is <= max_jump_px (0 = any). Sorted, all cameras together."""
    out: list[float] = []
    for pts in samples.values():
        det = sorted((s for s in pts if s.px is not None), key=lambda s: (s.t_s, s.seq))
        run: list[BallSample] = []
        for s in det:
            if run:
                prev = run[-1]
                jump = ((s.px[0] - prev.px[0]) ** 2 + (s.px[1] - prev.px[1]) ** 2) ** 0.5  # type: ignore[index]
                if s.seq - prev.seq > max_seq_gap or (max_jump_px > 0 and jump > max_jump_px):
                    if len(run) >= min_run:
                        out.extend(r.t_s for r in run)
                    run = []
            run.append(s)
        if len(run) >= min_run:
            out.extend(r.t_s for r in run)
    out.sort()
    return out


def _gaps(tracked: list[float], gap_s: float) -> list[float]:
    """Dead-ball times: gap_s after any tracked time that is followed by more than gap_s without one (or by nothing)."""
    out: list[float] = []
    for i, t in enumerate(tracked):
        nxt = tracked[i + 1] if i + 1 < len(tracked) else None
        if nxt is None or nxt - t > gap_s:
            out.append(t + gap_s)
    return out


def _side_before(bounces: list[tuple[float, str, str]], t: float) -> str | None:
    before = [b for b in bounces if b[0] <= t]
    return before[-1][1] if before else None

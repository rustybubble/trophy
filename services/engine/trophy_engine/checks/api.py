"""The API a check may use: the field, the 3D track, and the maths. Checks import only this module.

A check is a file in ``checks/`` with ``PARAMS`` (its defaults) and ``check(track, field, params=None, **q)``
returning a ``CheckResult`` dict (``result()`` builds one). Pure functions only: no I/O, no network, no imports
outside ``trophy_engine.checks.library.ALLOWED_IMPORTS``. The Droid edits the checks; this module is fixed.

Frame: origin at the play-surface centre, x along the length (side A: x < 0, side B: x > 0), y across, z up.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from trophy_engine.sportmod.api import fuse, phi, rect_line_distances, side_of  # noqa: F401  (re-exported)

Side = str  # "A" | "B"
G = 9.81


# ---------------------------------------------------------------- the field


@dataclass(frozen=True)
class Field:
    """The calibration (``field.json``, trophy.field.v1) as a check sees it."""

    sport: str
    length_m: float
    width_m: float
    cx_m: float  # table centre in the field frame (normally 0, 0)
    cy_m: float
    surface_z_m: float
    floor_z_m: float
    net_x_m: float
    net_height_m: float
    ball_r_m: float
    sigma_default_m: float
    sigma_1view_m: float
    skew_sigma_s: float
    calibrated: bool  # the field carries an uncertainty model
    raw: Mapping[str, Any]

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Field:
        corners = d.get("corners_m") or []
        if len(corners) == 4:
            xs = [float(c[0]) for c in corners]
            ys = [float(c[1]) for c in corners]
            length = max(xs) - min(xs)
            width = max(ys) - min(ys)
            cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
            surface_z = float(d.get("surface_z_m", sum(float(c[2]) for c in corners) / 4))
        else:
            table = d.get("table") or {}
            length, width = float(table.get("length_m", 2.74)), float(table.get("width_m", 1.525))
            cx, cy = 0.0, 0.0
            surface_z = float(d.get("surface_z_m", 0.0))
        table = d.get("table") or {}
        floor_z = float(d.get("floor_z_m", surface_z - float(table.get("height_m", 0.76))))
        net = d.get("net") or {}
        unc = d.get("uncertainty") or {}
        ball = d.get("ball") or {}
        return cls(
            sport=str(d.get("sport", "table_tennis")),
            length_m=length,
            width_m=width,
            cx_m=cx,
            cy_m=cy,
            surface_z_m=surface_z,
            floor_z_m=floor_z,
            net_x_m=float(net.get("x_m", cx)),
            net_height_m=float(net.get("height_m", 0.1525)),
            ball_r_m=float(ball.get("diameter_m", 0.040)) / 2,
            sigma_default_m=float(unc.get("sigma_default_m", 0.03)),
            sigma_1view_m=float(unc.get("sigma_1view_m", unc.get("sigma_default_m", 0.03))),
            skew_sigma_s=float(unc.get("skew_sigma_s", (d.get("time") or {}).get("skew_sigma_s", 0.0))),
            calibrated=bool(unc),
            raw=d,
        )

    @property
    def half_l(self) -> float:
        return self.length_m / 2

    @property
    def half_w(self) -> float:
        return self.width_m / 2

    def lines(self, x: float, y: float) -> dict[str, float]:
        """Signed distance (+ inside) to end_A, end_B, side_right, side_left."""
        return rect_line_distances(x - self.cx_m, y - self.cy_m, self.length_m, self.width_m)

    def d_min(self, x: float, y: float) -> tuple[str, float]:
        name, d = min(self.lines(x, y).items(), key=lambda kv: kv[1])
        return name, d

    def side(self, x: float) -> Side:
        return side_of(x, self.net_x_m)

    def inside(self, x: float, y: float, margin_m: float = 0.0) -> bool:
        return self.d_min(x, y)[1] >= -margin_m

    def in_serve_zone(self, x: float, z: float, behind_m: float, z_lo: float, z_hi: float) -> bool:
        """Near or behind an end line, at hand height: where a serve starts."""
        return abs(x - self.cx_m) >= self.half_l - behind_m and z_lo <= z - self.surface_z_m <= z_hi


# ---------------------------------------------------------------- the track


@dataclass(frozen=True)
class Sample:
    t: float
    x: float
    y: float
    z: float
    sigma: float
    conf: float
    n_views: int
    has_sigma: bool

    @property
    def xyz(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def sample_from_row(row: Mapping[str, Any], field: Field) -> Sample:
    """Adapt one provisional ``track3d`` row (interfaces: track3d.schema.json). Missing sigma -> the field default."""
    xyz = row["xyz_m"]
    n_views = int(row.get("n_views", 2))
    sigma = row.get("sigma_m")
    has_sigma = sigma is not None
    if sigma is None and row.get("cov_m2"):
        c = row["cov_m2"]
        sigma = math.sqrt(max((float(c[0]) + float(c[4]) + float(c[8])) / 3.0, 1e-12))
        has_sigma = True
    if sigma is None:
        sigma = field.sigma_1view_m if n_views <= 1 else field.sigma_default_m
    return Sample(
        t=float(row["t_s"]),
        x=float(xyz[0]),
        y=float(xyz[1]),
        z=float(xyz[2]),
        sigma=max(float(sigma), 1e-4),
        conf=float(row.get("conf", 1.0)),
        n_views=n_views,
        has_sigma=has_sigma,
    )


class Track:
    """Fused ball samples, time-ordered. Immutable from a check's point of view."""

    def __init__(self, samples: Iterable[Sample]) -> None:
        self.samples: list[Sample] = sorted(samples, key=lambda s: s.t)
        self.calibrated = all(s.has_sigma for s in self.samples) if self.samples else False

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]], field: Field) -> Track:
        return cls(sample_from_row(r, field) for r in rows)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, i: int) -> Sample:
        return self.samples[i]

    def __iter__(self):
        return iter(self.samples)

    @property
    def t0(self) -> float:
        return self.samples[0].t if self.samples else 0.0

    @property
    def t1(self) -> float:
        return self.samples[-1].t if self.samples else 0.0

    def window(self, t0: float | None = None, t1: float | None = None) -> Track:
        lo = -math.inf if t0 is None else t0
        hi = math.inf if t1 is None else t1
        return Track(s for s in self.samples if lo <= s.t <= hi)

    def good(self, min_conf: float) -> Track:
        return Track(s for s in self.samples if s.conf >= min_conf)

    def velocity(self, i: int) -> tuple[float, float, float]:
        """Central-difference velocity at sample i (one-sided at the ends); zero for a single sample."""
        n = len(self.samples)
        if n < 2:
            return (0.0, 0.0, 0.0)
        a = self.samples[max(0, i - 1)]
        b = self.samples[min(n - 1, i + 1)]
        dt = b.t - a.t
        if dt <= 1e-9:
            return (0.0, 0.0, 0.0)
        return ((b.x - a.x) / dt, (b.y - a.y) / dt, (b.z - a.z) / dt)

    def speed(self, i: int) -> float:
        vx, vy, vz = self.velocity(i)
        return math.sqrt(vx * vx + vy * vy + vz * vz)

    MAX_STEP_S = 0.2  # consecutive samples farther apart than this are not one flight (the ball was lost)
    MAX_SPEED_M_S = 45.0  # faster than any ball: the track jumped (lost and re-found), not one flight

    def step_velocity(self, i: int) -> tuple[float, float, float]:
        """Velocity over the step ending at sample i (samples i-1 -> i); zero across a gap."""
        if i <= 0 or i >= len(self.samples):
            return (0.0, 0.0, 0.0)
        a, b = self.samples[i - 1], self.samples[i]
        if not self._one_flight(a, b):
            return (0.0, 0.0, 0.0)
        dt = b.t - a.t
        return ((b.x - a.x) / dt, (b.y - a.y) / dt, (b.z - a.z) / dt)

    def _one_flight(self, a: Sample, b: Sample) -> bool:
        dt = b.t - a.t
        if dt <= 1e-9 or dt > self.MAX_STEP_S:
            return False
        return math.dist(a.xyz, b.xyz) / dt <= self.MAX_SPEED_M_S

    def contiguous(self, i: int, j: int) -> bool:
        """True when every step between samples i and j is one flight (no time gap, no jump)."""
        s = self.samples
        return all(self._one_flight(s[k], s[k + 1]) for k in range(max(0, i), min(j, len(s) - 1)))

    def mean_velocity(self, i: int, j: int) -> tuple[float, float, float]:
        """Mean velocity from sample i to sample j (clamped), zero across a gap."""
        n = len(self.samples)
        i, j = max(0, i), min(n - 1, j)
        if j <= i or not self.contiguous(i, j):
            return (0.0, 0.0, 0.0)
        a, b = self.samples[i], self.samples[j]
        dt = b.t - a.t
        return ((b.x - a.x) / dt, (b.y - a.y) / dt, (b.z - a.z) / dt)

    def index_at(self, t: float) -> int:
        """Index of the last sample with sample.t <= t (0 if none)."""
        lo, hi = 0, len(self.samples) - 1
        if hi < 0:
            return 0
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.samples[mid].t <= t:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def at(self, t: float) -> tuple[float, float, float]:
        """Linear interpolation of the position at time t (clamped to the ends)."""
        if not self.samples:
            return (math.nan, math.nan, math.nan)
        i = self.index_at(t)
        a = self.samples[i]
        if i + 1 >= len(self.samples) or t <= a.t:
            return a.xyz
        b = self.samples[i + 1]
        u = (t - a.t) / max(b.t - a.t, 1e-9)
        u = max(0.0, min(1.0, u))
        return (a.x + u * (b.x - a.x), a.y + u * (b.y - a.y), a.z + u * (b.z - a.z))

    def sigma_at(self, t: float) -> float:
        i = self.index_at(t)
        return self.samples[i].sigma if self.samples else math.inf

    def gaps(self, min_gap_s: float) -> list[tuple[float, float]]:
        """(t_last_seen, t_next_seen) pairs where no sample exists for at least min_gap_s."""
        out = []
        for a, b in zip(self.samples, self.samples[1:], strict=False):
            if b.t - a.t >= min_gap_s:
                out.append((a.t, b.t))
        return out

    def local_minima_z(self) -> list[int]:
        """Indices i with z[i-1] > z[i] <= z[i+1] within one flight (a bounce, or a racket hit at the low point)."""
        s = self.samples
        return [i for i in range(1, len(s) - 1) if s[i - 1].z > s[i].z <= s[i + 1].z and self.contiguous(i - 1, i + 1)]

    def local_maxima_z(self) -> list[int]:
        s = self.samples
        return [i for i in range(1, len(s) - 1) if s[i - 1].z < s[i].z >= s[i + 1].z and self.contiguous(i - 1, i + 1)]

    def reversals(self, axis: int, min_speed: float = 0.4) -> list[int]:
        """Indices i where velocity component `axis` (0 x, 1 y, 2 z) changes sign between the step into i and the
        step out of i, with at least one side faster than min_speed."""
        out = []
        for i in range(1, len(self.samples) - 1):
            vin = self.step_velocity(i)[axis]
            vout = self.step_velocity(i + 1)[axis]
            if vin * vout < 0 and (abs(vin) > min_speed or abs(vout) > min_speed):
                out.append(i)
        return out

    def vx_reversals(self) -> list[int]:
        return self.reversals(0)


# ---------------------------------------------------------------- maths


def parabola_vertex(t0: float, y0: float, t1: float, y1: float, t2: float, y2: float) -> tuple[float, float]:
    """Vertex (t, y) of the parabola through three points; the middle point when degenerate or outside [t0, t2]."""
    d = (t0 - t1) * (t0 - t2) * (t1 - t2)
    if abs(d) < 1e-12:
        return t1, y1
    a = (t2 * (y1 - y0) + t1 * (y0 - y2) + t0 * (y2 - y1)) / d
    b = (t2 * t2 * (y0 - y1) + t1 * t1 * (y2 - y0) + t0 * t0 * (y1 - y2)) / d
    c = (t1 * t2 * (t1 - t2) * y0 + t2 * t0 * (t2 - t0) * y1 + t0 * t1 * (t0 - t1) * y2) / d
    if abs(a) < 1e-12:
        return t1, y1
    tv = -b / (2 * a)
    if not (t0 <= tv <= t2):
        return t1, y1
    return tv, a * tv * tv + b * tv + c


def refine_extremum(track: Track, i: int) -> tuple[float, float, float, float]:
    """Sub-sample time, x, y and z of the z extremum around sample i (parabola through i-1, i, i+1)."""
    s = track.samples
    if i <= 0 or i >= len(s) - 1:
        return s[i].t, s[i].x, s[i].y, s[i].z
    t, z = parabola_vertex(s[i - 1].t, s[i - 1].z, s[i].t, s[i].z, s[i + 1].t, s[i + 1].z)
    x, y, _ = track.at(t)
    return t, x, y, z


def quad_fit(ts: list[float], zs: list[float]) -> tuple[float, float, float] | None:
    """Least-squares z = a t^2 + b t + c (t re-centred internally); None when fewer than 3 points or degenerate.
    Returns the vertex (t, z) and the curvature a."""
    n = len(ts)
    if n < 3:
        return None
    t0 = sum(ts) / n
    u = [t - t0 for t in ts]
    s0, s1, s2, s3, s4 = n, sum(u), sum(x * x for x in u), sum(x**3 for x in u), sum(x**4 for x in u)
    y0, y1, y2 = (
        sum(zs),
        sum(x * z for x, z in zip(u, zs, strict=False)),
        sum(x * x * z for x, z in zip(u, zs, strict=False)),
    )
    # solve [[s4,s3,s2],[s3,s2,s1],[s2,s1,s0]] [a,b,c] = [y2,y1,y0]
    m = [[s4, s3, s2, y2], [s3, s2, s1, y1], [s2, s1, s0, y0]]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-15:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(3):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[col], strict=False)]
    a, b, c = (m[r][3] / m[r][r] for r in range(3))
    if abs(a) < 1e-9:
        return None
    tv = -b / (2 * a)
    return (t0 + tv, a * tv * tv + b * tv + c, a)


def line_fit_angle(points: list[tuple[float, float, float]]) -> float:
    """Angle from vertical of the least-squares line through 3D points, fitting x(z) and y(z): robust to noise on
    single samples. Falls back to the end-to-end displacement with fewer than 3 points."""
    n = len(points)
    if n < 3:
        if n == 2:
            return angle_from_vertical(
                points[1][0] - points[0][0], points[1][1] - points[0][1], points[1][2] - points[0][2]
            )
        return 0.0
    zs = [p[2] for p in points]
    zm = sum(zs) / n
    var = sum((z - zm) ** 2 for z in zs)
    if var < 1e-9:
        return math.pi / 2
    sx = sum((p[2] - zm) * (p[0] - sum(q[0] for q in points) / n) for p in points) / var
    sy = sum((p[2] - zm) * (p[1] - sum(q[1] for q in points) / n) for p in points) / var
    return math.atan(math.hypot(sx, sy))


def line_fit(ts: list[float], vs: list[float]) -> tuple[float, float] | None:
    """Least squares v = a + b t; None with fewer than 2 distinct times."""
    n = len(ts)
    if n < 2:
        return None
    tm = sum(ts) / n
    vm = sum(vs) / n
    var = sum((t - tm) ** 2 for t in ts)
    if var < 1e-12:
        return None
    b = sum((t - tm) * (v - vm) for t, v in zip(ts, vs, strict=False)) / var
    return (vm - b * tm, b)


def refine_bounce(
    track: Track, i: int, plane_z: float | None = None, n_fit: int = 4
) -> tuple[float, float, float, float, float, bool, float]:
    """Sub-sample bounce around the low sample i, from the incoming flight alone.

    In free flight z(t) + g t^2 / 2 is a straight line, so the samples before the bounce give the incoming path
    exactly (no parabola bias, no dependence on the rebound, which may be weak or missing a sample). The bounce
    instant is where that path reaches ``plane_z`` (the surface, or the floor); x and y come from the incoming
    x(t), y(t) lines at that instant. Which samples are still incoming is not known a priori (the low sample may be
    just before or just after the bounce), so every split within the last few samples is tried and the one whose
    incoming line fits best, reaches the plane between its last sample and the next, and leaves the next sample no
    higher than a rebound allows, wins. Returns (t, x, y, z, dt_sigma, solved, v_in): ``solved`` is False when no
    split works (a low point in the air, or too few samples), in which case the parabola vertex is returned; the
    last value is the incoming speed, which the position sigma scales with (6 ms at 5 m/s is 3 cm).
    """
    s = track.samples
    t_par, x_par, y_par, z_par = refine_extremum(track, i)
    v_fallback = track.speed(max(0, i - 1))
    fallback = (t_par, x_par, y_par, z_par, 0.012, False, v_fallback)
    if plane_z is None or i < 2:
        return fallback
    lo = i
    while lo > 0 and i - lo < n_fit + 1 and track._one_flight(s[lo - 1], s[lo]):
        lo -= 1
    if i - lo < 1:
        return fallback
    t0 = s[i].t

    def wfit(samples: list[Sample]):
        return line_fit([q.t - t0 for q in samples], [q.z + 0.5 * G * (q.t - t0) ** 2 for q in samples])

    best = None
    for k in range(i, max(lo, i - 3) - 1, -1):  # k = the last incoming sample
        inc = list(s[max(lo, k - n_fit) : k + 1])
        if len(inc) < 2:
            continue
        fw = wfit(inc)
        if fw is None:
            continue
        a, b = fw
        u_k = inc[-1].t - t0
        if b - G * u_k >= 0:
            continue  # not descending at the split
        disc = b * b + 2 * G * (a - plane_z)
        if disc < 0:
            continue
        roots = [(b + math.sqrt(disc)) / G, (b - math.sqrt(disc)) / G]  # z(u) = a + b u - g u^2/2 = plane
        nxt = s[k + 1] if k + 1 < len(s) else None
        hi = (nxt.t - t0 + 0.005) if nxt is not None else (u_k + 0.06)
        cands = [u for u in roots if u_k - 0.005 <= u <= hi]
        if not cands:
            continue
        u = min(cands, key=lambda v: abs(v - u_k))
        vz_star = b - G * u
        v_abs = abs(vz_star)
        # the next sample is post-bounce: it can be no higher than a full-restitution rebound puts it
        if nxt is not None and nxt.z - plane_z > v_abs * (nxt.t - t0 - u) + 0.04:
            continue
        res = [q.z + 0.5 * G * (q.t - t0) ** 2 - (a + b * (q.t - t0)) for q in inc]
        rms = math.sqrt(sum(r * r for r in res) / len(res)) if len(res) > 2 else 0.012
        score = rms / math.sqrt(len(inc))  # prefer a clean fit, then more samples
        if best is None or score < best[0]:
            best = (score, u, inc, a, b, vz_star, rms)
    if best is None:
        return fallback
    _, u, inc, a, b, vz_star, rms = best
    t_star = t0 + u
    fx = line_fit([q.t - t0 for q in inc], [q.x for q in inc])
    fy = line_fit([q.t - t0 for q in inc], [q.y for q in inc])
    x_star = fx[0] + fx[1] * u if fx else x_par
    y_star = fy[0] + fy[1] * u if fy else y_par
    dt_sigma = max(0.003, min(0.03, max(rms, 0.008) / max(abs(vz_star), 0.5)))
    v_in = math.sqrt((fx[1] if fx else 0.0) ** 2 + (fy[1] if fy else 0.0) ** 2 + vz_star * vz_star)
    return t_star, x_star, y_star, plane_z, dt_sigma, True, v_in


def leg_angle(samples: list[Sample], t0: float, t1: float, z0: float | None = None, z1: float | None = None) -> float:
    """Angle from vertical of a toss leg between t0 and t1: x(t), y(t) are fitted as lines (constant horizontal
    velocity in flight) and evaluated at both ends; the vertical extent is z1 - z0 (given, e.g. the fitted apex and
    the release height) or the fitted z(t) line's end values."""
    if len(samples) < 2:
        return 0.0
    ts = [q.t for q in samples]
    fx = line_fit(ts, [q.x for q in samples])
    fy = line_fit(ts, [q.y for q in samples])
    if fx is None or fy is None:
        return 0.0
    dx = fx[1] * (t1 - t0)
    dy = fy[1] * (t1 - t0)
    if z0 is None or z1 is None:
        fz = quad_fit(ts, [q.z for q in samples])
        if fz is None:
            fl = line_fit(ts, [q.z for q in samples])
            dz = fl[1] * (t1 - t0) if fl else 0.0
        else:
            tv, zv, a = fz
            # z(t) = a (t - tv)^2 + zv
            dz = (a * (t1 - tv) ** 2 + zv) - (a * (t0 - tv) ** 2 + zv)
    else:
        dz = z1 - z0
    return angle_from_vertical(dx, dy, dz)


def interp_crossing(a: Sample, b: Sample, value: float, axis: str = "x") -> tuple[float, float, float, float]:
    """Time and position where the segment a->b crosses axis == value (linear)."""
    va, vb = getattr(a, axis), getattr(b, axis)
    u = 0.0 if abs(vb - va) < 1e-12 else (value - va) / (vb - va)
    u = max(0.0, min(1.0, u))
    return (a.t + u * (b.t - a.t), a.x + u * (b.x - a.x), a.y + u * (b.y - a.y), a.z + u * (b.z - a.z))


def angle_from_vertical(dx: float, dy: float, dz: float) -> float:
    """Angle (rad) between a displacement and the vertical axis."""
    h = math.hypot(dx, dy)
    return math.atan2(h, abs(dz)) if (h > 0 or dz != 0) else 0.0


def motion_sigma(sigma_m: float, speed_m_s: float, skew_sigma_s: float) -> float:
    """Position sigma inflated by timing skew: a ball at v with skew s is off by v*s."""
    return math.sqrt(sigma_m * sigma_m + (speed_m_s * skew_sigma_s) ** 2)


def edge_probs(d_min: float, sigma: float, edge_band_m: float, z_rel: float, sigma_z: float) -> dict[str, float] | None:
    """Within the edge band: P(top edge) / P(side face) / P(surface, i.e. clearly in). Else None.

    ``d_min`` is the signed distance to the nearest line (+ inside); ``z_rel`` the bounce height relative to the
    surface. A contact below the surface pushes probability to the side face.
    """
    f_band = 1.0 - phi((abs(d_min) - edge_band_m) / max(sigma, 1e-6))  # P(within the band)
    if f_band < 0.05:
        return None
    p_in = phi(d_min / max(sigma, 1e-6))
    p_below = 1.0 - phi((z_rel + 0.5 * edge_band_m) / max(sigma_z, 1e-6))  # clearly below the top -> side face
    p_side = (1.0 - p_in) * (1.0 - p_below) + p_below
    p_side = max(0.0, min(1.0, p_side))
    top = f_band * (1.0 - p_side)
    side = f_band * p_side
    surface = 1.0 - f_band
    return {"top_edge": top, "side_face": side, "surface": surface}


def merge_params(defaults: Mapping[str, Any], params: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(defaults)
    if params:
        out.update({k: v for k, v in params.items() if k in defaults})
    return out


def rnd(v: Any, nd: int = 4) -> Any:
    """Round floats (recursively) so results are deterministic and diff-friendly."""
    if isinstance(v, float):
        return round(v, nd)
    if isinstance(v, dict):
        return {k: rnd(x, nd) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [rnd(x, nd) for x in v]
    return v


def result(
    check: str,
    verdict: Any,
    *,
    p: float | None = None,
    t_s: float | None = None,
    sigma_m: float | None = None,
    evidence: Mapping[str, Any] | None = None,
    calibrated: bool = True,
    text: str = "",
) -> dict[str, Any]:
    """Build a CheckResult (track3d.schema.json $defs.CheckResult)."""
    out: dict[str, Any] = {
        "check": check,
        "verdict": rnd(verdict),
        "p": None if p is None else round(max(0.0, min(1.0, float(p))), 4),
        "t_s": None if t_s is None else round(float(t_s), 4),
        "sigma_m": None if sigma_m is None else round(float(sigma_m), 4),
        "evidence": rnd(dict(evidence or {})),
        "calibrated": bool(calibrated),
        "text": text,
    }
    return out

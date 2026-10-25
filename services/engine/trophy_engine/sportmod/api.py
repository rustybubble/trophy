"""The API a sport module's ``events.py`` may use: observations in, layer-2 events out.

A module implements ``events(observations, state) -> Iterable[dict]``. Observations are ``Camera`` and ``BallSample``
records (layer 1, read from a JSONL log or Spacetime). Events are ``trophy.event.v1`` dicts built with the helpers here;
the loader validates every one against the contract. Pure functions only: no I/O, no network, no imports outside
``trophy_engine.sportmod.loader.ALLOWED_IMPORTS``.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

Side = str  # "A" | "B"


@dataclass(frozen=True)
class Camera:
    """A camera row's calibration, as the module sees it."""

    cam_id: str
    image_w: int
    image_h: int
    H_img_to_field: tuple[float, ...]  # 9 floats, row-major, px -> field metres on the play plane
    trusted: bool
    reproj_err_px: float
    fps: float

    def to_field(self, u: float, v: float) -> tuple[float, float]:
        return apply_h(self.H_img_to_field, u, v)


@dataclass(frozen=True)
class BallSample:
    """One ball detection (or a miss when ``px`` is None) from one camera."""

    cam_id: str
    t_s: float
    seq: int
    px: tuple[float, float] | None
    conf: float


Observation = Camera | BallSample


@dataclass
class ModuleState:
    """What the worker gives the module besides observations."""

    game_id: str
    sport: str
    config: Mapping[str, Any]  # config.yaml
    field_lines: Mapping[str, Any] = field(default_factory=dict)  # rules.yaml field.lines
    calib_trusted: bool = True


# ---------------------------------------------------------------- maths


def apply_h(H: tuple[float, ...] | list[float], u: float, v: float) -> tuple[float, float]:
    """Apply a 3x3 row-major homography to an image point."""
    x = H[0] * u + H[1] * v + H[2]
    y = H[3] * u + H[4] * v + H[5]
    w = H[6] * u + H[7] * v + H[8]
    if abs(w) < 1e-12:
        return (math.inf, math.inf)
    return (x / w, y / w)


def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def rect_line_distances(x: float, y: float, length_m: float, width_m: float) -> dict[str, float]:
    """Signed distances (+ = inside) to the four lines of a court/table centred at the origin, x along the length."""
    return {
        "end_A": x + length_m / 2,
        "end_B": length_m / 2 - x,
        "side_right": y + width_m / 2,
        "side_left": width_m / 2 - y,
    }


def side_of(x: float, net_x_m: float = 0.0) -> Side:
    return "A" if x < net_x_m else "B"


def fuse(values: Iterable[tuple[float, float]]) -> tuple[float, float]:
    """Inverse-variance weighted mean of (value, sigma) pairs -> (mean, sigma)."""
    num = 0.0
    den = 0.0
    for v, s in values:
        w = 1.0 / max(s * s, 1e-12)
        num += w * v
        den += w
    if den == 0.0:
        return (math.nan, math.inf)
    return (num / den, math.sqrt(1.0 / den))


# ---------------------------------------------------------------- event builders


def _event_id(game_id: str, type_: str, t_s: float, cams: Iterable[str]) -> str:
    """Deterministic 26-char Crockford id so replays are reproducible (replay_test checks determinism)."""
    h = hashlib.blake2b(f"{game_id}|{type_}|{t_s:.4f}|{','.join(sorted(cams))}".encode(), digest_size=16).digest()
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    n = int.from_bytes(h, "big")
    out = []
    for _ in range(26):
        out.append(alphabet[n & 31])
        n >>= 5
    return "".join(reversed(out))


def _base(state: ModuleState, type_: str, t_s: float, cams: list[str], conf: float, **extra: Any) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "schema": "trophy.event.v1",
        "id": _event_id(state.game_id, type_, t_s, cams),
        "game_id": state.game_id,
        "t_game_s": round(t_s, 4),
        "sport": state.sport,
        "type": type_,
        "source": "flight",
        "cams": list(cams),
        "conf": max(0.0, min(1.0, conf)),
    }
    ev.update({k: v for k, v in extra.items() if v is not None})
    return ev


def bounce_event(
    state: ModuleState,
    *,
    t_s: float,
    cams: list[str],
    surface: str,
    side: Side,
    x: float,
    y: float,
    sigma_m: float,
    d_lines_m: Mapping[str, float],
    p_in: float,
    edge: Mapping[str, float] | None,
    conf: float,
    timing: str = "track",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "surface": surface,
        "side": side,
        "d_lines_m": {k: round(v, 4) for k, v in d_lines_m.items()},
        "p_in": round(max(0.0, min(1.0, p_in)), 4),
        "edge": {k: round(v, 4) for k, v in edge.items()} if edge else None,
        "timing": timing,
    }
    if not state.calib_trusted:
        payload["calib_untrusted"] = True
    return _base(
        state,
        "bounce",
        t_s,
        cams,
        conf,
        side=side,
        pos_m={"x": round(x, 4), "y": round(y, 4), "z": 0.0},
        sigma_m=round(sigma_m, 4),
        payload=payload,
    )


def net_event(
    state: ModuleState, *, t_s: float, cams: list[str], kind: str, from_side: Side, conf: float
) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": kind, "from_side": from_side}
    if not state.calib_trusted:
        payload["calib_untrusted"] = True
    return _base(state, "net", t_s, cams, conf, side=from_side, payload=payload)


def ball_dead_event(
    state: ModuleState, *, t_s: float, cams: list[str], reason: str, last_side: Side | None, conf: float
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason": reason}
    if last_side is not None:
        payload["last_side"] = last_side
    return _base(state, "ball_dead", t_s, cams, conf, side=last_side, payload=payload)


def contact_event(
    state: ModuleState, *, t_s: float, cams: list[str], side: Side, kind: str, conf: float
) -> dict[str, Any]:
    return _base(state, "contact", t_s, cams, conf, side=side, payload={"side": side, "kind": kind})

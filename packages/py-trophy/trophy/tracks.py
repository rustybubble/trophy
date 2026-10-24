"""Track streams (interfaces-v1 §8): ``trk:ball:{cam}`` and ``trk:players:{cam}``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import redis

from .contracts import BallTrackSample, PlayersTrackSample
from .streams import trk_ball_key, trk_players_key

BALL_MAXLEN = 20_000
PLAYERS_MAXLEN = 20_000


def _dump(sample: Any) -> str:
    if isinstance(sample, Mapping):
        return json.dumps(sample, separators=(",", ":"))
    return sample.model_dump_json(exclude_unset=True)  # keeps px: null, which is required


class BallTrackWriter:
    def __init__(self, r: redis.Redis, cam_id: str) -> None:
        self.r, self.key = r, trk_ball_key(cam_id)

    def write(self, sample: BallTrackSample | Mapping[str, Any]) -> None:
        if isinstance(sample, Mapping):
            sample = BallTrackSample.model_validate(sample)
        self.r.xadd(self.key, {"json": _dump(sample)}, maxlen=BALL_MAXLEN, approximate=True)


class PlayersTrackWriter:
    def __init__(self, r: redis.Redis, cam_id: str) -> None:
        self.r, self.key = r, trk_players_key(cam_id)

    def write(self, sample: PlayersTrackSample | Mapping[str, Any]) -> None:
        if isinstance(sample, Mapping):
            sample = PlayersTrackSample.model_validate(sample)
        self.r.xadd(self.key, {"json": _dump(sample)}, maxlen=PLAYERS_MAXLEN, approximate=True)


def read_ball_track(r: redis.Redis, cam_id: str, t0_s: float, t1_s: float) -> list[BallTrackSample]:
    """Samples with t0_s <= t_game_s <= t1_s, oldest first (replay overlays)."""
    out = []
    for _id, fields in r.xrevrange(trk_ball_key(cam_id)):
        s = BallTrackSample.model_validate_json(fields.get(b"json", fields.get("json")))
        if s.t_game_s < t0_s:
            break
        if s.t_game_s <= t1_s:
            out.append(s)
    out.reverse()
    return out


class Downsampler:
    """Accepts at most ``hz`` samples per second of game time (per key, e.g. per camera)."""

    def __init__(self, hz: float = 10.0) -> None:
        self.period = 1.0 / hz
        self.next_t: dict[str, float] = {}

    def accept(self, t_game_s: float, key: str = "") -> bool:
        p = self.period
        nxt = self.next_t.get(key)
        if nxt is not None and nxt - 2 * p <= t_game_s < nxt - 0.25 * p:
            return False
        # Stay on the grid (frame jitter doesn't lower the rate); a gap or a jump back in time
        # (e.g. a clip restarting) re-anchors it.
        on_grid = nxt is not None and nxt - 0.25 * p <= t_game_s < nxt + p
        self.next_t[key] = (nxt if on_grid else t_game_s) + p
        return True

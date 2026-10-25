"""Events from a 3D track: the checks find rallies, bounces, contacts, nets and serves; this turns them into
``trophy.event.v1`` events for the rule engine, live (sample by sample, with a small confirmation lag) or in batch.

The eventer is deterministic for a given sample order. It emits, per rally: ``serve_toss`` at the serve hit,
``bounce`` / ``contact`` / ``net`` in time order, and ``ball_dead`` when `phases` closes the rally. Every event
carries ``rally_no_hint`` (the phases' rally number) for consumers that drop events after a scored point.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from ..sportmod.api import ModuleState, _base, ball_dead_event, bounce_event, contact_event, net_event
from .api import Field, Sample, Track, sample_from_row
from .library import CheckLibrary

EVENT_TYPES = ("serve_toss", "bounce", "contact", "net", "ball_dead")


class TrackEventer:
    def __init__(
        self,
        library: CheckLibrary,
        fld: Field,
        *,
        game_id: str,
        sport: str | None = None,
        params: Mapping[str, Mapping[str, Any]] | None = None,
        lag_s: float = 0.07,
        cams: list[str] | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.lib = library
        self.field = fld
        self.params = {k: dict(v) for k, v in (params or {}).items()}
        self.lag_s = lag_s
        self.cams = cams or [c.get("cam_id", "cam") for c in (fld.raw.get("cameras") or [])] or ["track3d"]
        self.state = ModuleState(game_id=game_id, sport=sport or fld.sport, config=dict(config or {}))
        self.samples: list[Sample] = []
        self.emitted: list[tuple[str, float]] = []  # (type, t) already emitted
        self.rally_state: dict[int, dict[str, Any]] = {}  # rally_no -> {"served": bool, "closed": bool}
        self.last_rally_no = 0
        self.calibrated = True
        self.last_phases: dict[str, Any] | None = None  # the latest `phases` verdict (segments + phase)

    # ------------------------------------------------------------ feeding

    def push(self, row: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Add one fused sample; return the events now confirmed (t <= now - lag)."""
        s = sample_from_row(row, self.field)
        if self.samples and s.t < self.samples[-1].t:
            return []  # out-of-order samples are dropped (the fusion stamps them in order)
        self.samples.append(s)
        return self._emit(now=s.t)

    def tick(self, now: float) -> list[dict[str, Any]]:
        """Time passed with no sample (the ball is lost): lets `phases` close a rally on the gap."""
        return self._emit(now=now)

    def feed_all(self, track: Track | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        rows = (
            [
                {
                    "t_s": s.t,
                    "xyz_m": [s.x, s.y, s.z],
                    "sigma_m": s.sigma if s.has_sigma else None,
                    "conf": s.conf,
                    "n_views": s.n_views,
                }
                for s in track
            ]
            if isinstance(track, Track)
            else list(track)
        )
        for r in rows:
            r = {k: v for k, v in r.items() if v is not None}
            out += self.push(r)
        if self.samples:
            out += self.tick(self.samples[-1].t + 5.0)
        return out

    # ------------------------------------------------------------ the work

    def _track(self) -> Track:
        return Track(self.samples)

    def _emit(self, now: float) -> list[dict[str, Any]]:
        if not self.samples:
            return []
        tr = self._track()
        self.calibrated = tr.calibrated
        horizon = now - self.lag_s
        ph = self.lib.run("phases", tr, self.field, self.params.get("phases"), t1=now)
        self.last_phases = ph["verdict"]
        out: list[dict[str, Any]] = []
        for seg in ph["verdict"]["segments"]:
            rn = int(seg["rally_no"])
            st = self.rally_state.setdefault(rn, {"served": False, "closed": False})
            if st["closed"]:
                continue
            t_start = float(seg["t_start_s"])
            t_end = seg.get("t_end_s")
            t1 = min(horizon, float(t_end)) if t_end is not None else horizon
            if t1 <= t_start:
                continue
            # the serve: once a contact exists after the toss, measure it
            if not st["served"]:
                ct = self.lib.run("contacts", tr, self.field, self.params.get("contacts"), t0=t_start, t1=t1)
                # measure the toss once the hit is in view and the samples after it have arrived (the hit is found
                # as a velocity kink, which needs three samples past it); keep trying until the window closes
                if ct["verdict"] and t1 >= float(ct["verdict"][0]["t_s"]) + 0.12:
                    sv = self.lib.run(
                        "serve_toss", tr.window(None, t1), self.field, self.params.get("serve_toss"), t_start=t_start
                    )
                    if sv["verdict"] != "no_serve":
                        st["served"] = True
                        out.append(self._serve_event(sv, rn))
                    elif t1 > t_start + 2.5:
                        st["served"] = True  # no toss measurable: give up for this rally
            bn = self.lib.run("bounces", tr, self.field, self.params.get("bounces"), t0=t_start, t1=t1)
            for b in bn["verdict"]:
                out.append(self._bounce_event(b, rn, bn["calibrated"]))
            ct = self.lib.run("contacts", tr, self.field, self.params.get("contacts"), t0=t_start, t1=t1)
            for c in ct["verdict"]:
                out.append(self._contact_event(c, rn))
            nt = self.lib.run("net_touch", tr, self.field, self.params.get("net_touch"), t0=t_start, t1=t1)
            for n in nt["verdict"]:
                out.append(self._net_event(n, rn))
            if t_end is not None and float(t_end) <= horizon:
                st["closed"] = True
                last_side = self._last_bounce_side(bn["verdict"])
                reason = {"floor": "floor", "lost": "lost", "stopped": "stopped"}.get(
                    str(seg.get("end_reason")), "lost"
                )
                ev = ball_dead_event(
                    self.state, t_s=float(t_end), cams=self.cams, reason=reason, last_side=last_side, conf=0.9
                )
                ev["rally_no_hint"] = rn
                out.append(ev)
        # dedupe against what was already emitted, order by time, remember
        fresh = []
        for ev in sorted(out, key=lambda e: (float(e["t_game_s"]), EVENT_TYPES.index(e["type"]))):
            key = (ev["type"], float(ev["t_game_s"]))
            if any(k[0] == key[0] and abs(k[1] - key[1]) < 0.05 for k in self.emitted):
                continue
            self.emitted.append(key)
            fresh.append(ev)
        return fresh

    @staticmethod
    def _last_bounce_side(bounces: list[dict[str, Any]]) -> str | None:
        tb = [b for b in bounces if b["surface"] == "table"]
        return tb[-1]["side"] if tb else None

    # ------------------------------------------------------------ builders

    def _bounce_event(self, b: Mapping[str, Any], rn: int, calibrated: bool) -> dict[str, Any]:
        x, y, z = b["pos_m"]
        surface = "floor" if b["surface"] in ("floor", "side_face") else "table"
        ev = bounce_event(
            self.state,
            t_s=float(b["t_s"]),
            cams=self.cams,
            surface=surface,
            side=b["side"],
            x=x,
            y=y,
            sigma_m=float(b["sigma_m"]),
            d_lines_m=b["d_lines_m"],
            p_in=float(b["p_in"]),
            edge=b.get("edge"),
            conf=float(b.get("conf", 0.9)),
        )
        ev["pos_m"]["z"] = round(float(z), 4)
        if b["surface"] == "side_face":
            ev["payload"]["side_face"] = True
        if not calibrated:
            ev["payload"]["calib_untrusted"] = True
        ev["rally_no_hint"] = rn
        return ev

    def _contact_event(self, c: Mapping[str, Any], rn: int) -> dict[str, Any]:
        ev = contact_event(self.state, t_s=float(c["t_s"]), cams=self.cams, side=c["side"], kind="racket", conf=0.8)
        ev["payload"]["height_m"] = round(float(c.get("height_m", 0.0)), 4)
        ev["rally_no_hint"] = rn
        return ev

    def _net_event(self, n: Mapping[str, Any], rn: int) -> dict[str, Any]:
        ev = net_event(
            self.state,
            t_s=float(n["t_s"]),
            cams=self.cams,
            kind=n["kind"],
            from_side=n["from_side"],
            conf=float(n.get("p", 0.8)),
        )
        ev["rally_no_hint"] = rn
        return ev

    def _serve_event(self, sv: Mapping[str, Any], rn: int) -> dict[str, Any]:
        v, e = sv["verdict"], sv["evidence"]
        rise, fall = float(e["rise_angle_rad"]), float(e["fall_angle_rad"])
        payload = {
            "server_side": e["server_side"],
            "release": {"t_s": e["release"]["t_s"], "pos_m": _pos(e["release"]["pos_m"])},
            "apex": {"t_s": e["apex"]["t_s"], "pos_m": _pos(e["apex"]["pos_m"])},
            "contact": {"t_s": e["contact"]["t_s"], "pos_m": _pos(e["contact"]["pos_m"])},
            "height_m": round(float(v["height_m"]), 4),
            "sigma_height_m": round(float(e["sigma_height_m"]), 4),
            "rise_angle_rad": round(rise, 4),
            "fall_angle_rad": round(fall, 4),
            "angle_from_vertical_rad": round(max(rise, fall), 4),
            "sigma_angle_rad": round(float(e["sigma_angle_rad"]), 4),
            "observable_plane": "mixed",
        }
        ev = _base(self.state, "serve_toss", float(sv["t_s"]), self.cams, 0.9, side=e["server_side"], payload=payload)
        ev["rally_no_hint"] = rn
        return ev


def _pos(p: list[float]) -> dict[str, float]:
    return {"x": round(float(p[0]), 4), "y": round(float(p[1]), 4), "z": round(float(p[2]), 4)}


def events_from_rows(
    library: CheckLibrary, fld: Field, rows: Iterable[Mapping[str, Any]], *, game_id: str, sport: str | None = None
) -> list[dict[str, Any]]:
    """Batch convenience: every event for a finished track."""
    return TrackEventer(library, fld, game_id=game_id, sport=sport).feed_all(rows)


def nan_free(ev: Mapping[str, Any]) -> bool:
    return not any(isinstance(v, float) and math.isnan(v) for v in ev.values())

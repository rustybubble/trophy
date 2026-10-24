"""The shared world state (interfaces-v1 §7.1, §8, D-21): vision modules mirror their events into the
Spacetime ``observation`` table and the 10 Hz ball track into ``track_sample``.

    from trophy.world import ObservationWriter, TrackSampleWriter
    with ObservationWriter() as obs, TrackSampleWriter() as trk:
        obs.post(event)                       # same Event you XADD to ev:flight
        trk.post(game_id, cam_id, t_game_s, pos_m=(x, y, z), px=(u, v), conf=0.9)

Writes go to the reducers ``post_observations(batch_json)`` / ``post_track_samples(batch_json)``, where
``batch_json`` is a JSON array string, over ``POST {SPACETIME_URI}/v1/database/{SPACETIME_MODULE}/call/<reducer>``
with ``Authorization: Bearer $SPACETIME_VISION_TOKEN``. A background thread batches every 100 ms (rally-
ending types flush at once). Writers never block or raise on the hot path: when Spacetime is down,
batches are dropped and counted. No video ever goes here.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from .contracts import Event
from .events import RALLY_ENDING_TYPES, event_dict
from .tracks import Downsampler

log = logging.getLogger("trophy.world")


class ReducerClient(Protocol):
    def call(self, reducer: str, *args: Any) -> None: ...


class SpacetimeClient:
    """Minimal reducer caller over Spacetime's HTTP API (stdlib only)."""

    def __init__(
        self,
        uri: str | None = None,
        module: str | None = None,
        token: str | None = None,
        timeout_s: float = 2.0,
    ) -> None:
        self.uri = (uri or os.environ.get("SPACETIME_URI", "http://127.0.0.1:3000")).rstrip("/")
        self.module = module or os.environ.get("SPACETIME_MODULE", "trophy")
        self.token = token if token is not None else os.environ.get("SPACETIME_VISION_TOKEN", "")
        self.timeout_s = timeout_s

    def call(self, reducer: str, *args: Any) -> None:
        req = urllib.request.Request(
            f"{self.uri}/v1/database/{self.module}/call/{reducer}",
            data=json.dumps(list(args)).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            resp.read()


class RecordingClient:
    """Test/offline client that records calls instead of sending them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.lock = threading.Lock()

    def call(self, reducer: str, *args: Any) -> None:
        with self.lock:
            self.calls.append((reducer, args))

    def rows(self, reducer: str) -> list[dict[str, Any]]:
        with self.lock:
            return [row for r, a in self.calls if r == reducer for row in json.loads(a[0])]


class _BatchWriter:
    reducer = ""

    def __init__(
        self,
        client: ReducerClient | None = None,
        flush_interval_s: float = 0.1,
        max_batch: int = 256,
        max_queue: int = 10_000,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.client = client or SpacetimeClient()
        self.flush_interval_s = flush_interval_s
        self.max_batch = max_batch
        self.q: deque[dict[str, Any]] = deque(maxlen=max_queue)
        self.on_error = on_error
        self.sent = 0
        self.dropped = 0
        self.errors = 0
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._last_err_log = 0.0
        self._t = threading.Thread(target=self._run, name=f"trophy.world.{self.reducer}", daemon=True)
        self._t.start()

    def _enqueue(self, row: dict[str, Any], immediate: bool = False) -> None:
        if len(self.q) == self.q.maxlen:
            self.dropped += 1
        self._idle.clear()
        self.q.append(row)
        if immediate or len(self.q) >= self.max_batch:
            self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.flush_interval_s)
            self._wake.clear()
            self._drain()
        self._drain()

    def _drain(self) -> None:
        while self.q:
            batch: list[dict[str, Any]] = []
            while self.q and len(batch) < self.max_batch:
                batch.append(self.q.popleft())
            try:
                self.client.call(self.reducer, json.dumps(batch, separators=(",", ":")))
                self.sent += len(batch)
            except Exception as e:  # never raise into the vision loop
                self.errors += 1
                self.dropped += len(batch)
                if self.on_error:
                    self.on_error(e)
                now = time.monotonic()
                if now - self._last_err_log > 5:
                    self._last_err_log = now
                    log.warning("spacetime %s failed (%s); dropped %d rows so far", self.reducer, e, self.dropped)
        self._idle.set()

    def flush(self, timeout_s: float = 2.0) -> bool:
        """Send everything queued now; returns True if the queue drained within ``timeout_s``."""
        self._wake.set()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not self.q and self._idle.wait(0.01):
                return True
            self._wake.set()
        return False

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self._t.join(timeout=3)

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class ObservationWriter(_BatchWriter):
    """Mirrors trophy.event.v1 events into the Spacetime ``observation`` table (one row per event id)."""

    reducer = "post_observations"

    def post(self, ev: Event | Mapping[str, Any]) -> None:
        row = event_dict(ev) if isinstance(ev, Event) else dict(ev)
        self._enqueue(row, immediate=row.get("type") in RALLY_ENDING_TYPES)


class TrackSampleWriter(_BatchWriter):
    """Writes the ball track to ``track_sample``, down-sampled to ``hz`` per camera (default 10 Hz)."""

    reducer = "post_track_samples"

    def __init__(self, *args: Any, hz: float = 10.0, **kwargs: Any) -> None:
        self.down = Downsampler(hz)
        super().__init__(*args, **kwargs)

    def post(
        self,
        game_id: str,
        cam_id: str,
        t_game_s: float,
        *,
        pos_m: Sequence[float] | None = None,
        px: Sequence[float] | None = None,
        conf: float,
        object: str = "ball",
    ) -> bool:
        """Returns False if the sample was dropped by the down-sampler."""
        if not self.down.accept(t_game_s, f"{cam_id}:{object}"):
            return False
        self._enqueue(
            {
                "cam_id": cam_id,
                "t_game_s": t_game_s,
                "game_id": game_id,
                "object": object,
                "pos_m": list(pos_m) if pos_m is not None else None,
                "px": list(px) if px is not None else None,
                "conf": conf,
            }
        )
        return True

"""The live memory the engine fills and the ask service reads: fused samples, the rally segments the `phases` check
found, the calls the engine posted and the score. Pure data behind one lock; no I/O."""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping
from typing import Any

from ..checks.api import Field, Sample, Track, sample_from_row
from ..checks.library import CheckLibrary

MAX_CALLS = 50


class TrackStore:
    """``push`` samples as they arrive; ``track()`` is a time-ordered snapshot for the checks."""

    def __init__(self, library: CheckLibrary, field: Field | None = None, *, sport: str = "table_tennis") -> None:
        self.library = library
        self.field = field
        self.sport = sport
        self.segments: list[dict[str, Any]] = []
        self.recent_calls: list[dict[str, Any]] = []
        self.score: dict[str, Any] = {}
        self._samples: list[Sample] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------ writers (the engine)

    def set_field(self, field: Field) -> None:
        with self._lock:
            self.field = field
            self.sport = field.sport or self.sport

    def push(self, row: Mapping[str, Any]) -> Sample:
        """Add one ``track3d`` row (out-of-order rows are kept; ``track()`` sorts)."""
        if self.field is None:
            raise RuntimeError("TrackStore.push before set_field")
        s = sample_from_row(row, self.field)
        with self._lock:
            self._samples.append(s)
        return s

    def extend(self, rows: Iterable[Mapping[str, Any]]) -> int:
        n = 0
        for r in rows:
            self.push(r)
            n += 1
        return n

    def set_segments(self, segments: Iterable[Mapping[str, Any]]) -> None:
        """The `phases` verdict's segments: [{rally_no, t_start_s, t_end_s|None, server_side, ...}]."""
        segs = [dict(s) for s in segments]
        segs.sort(key=lambda s: (float(s["t_start_s"]), int(s.get("rally_no", 0))))
        with self._lock:
            self.segments = segs

    def add_call(self, call: Mapping[str, Any]) -> None:
        with self._lock:
            self.recent_calls.append(dict(call))
            del self.recent_calls[:-MAX_CALLS]

    def set_score(self, score: Mapping[str, Any]) -> None:
        with self._lock:
            self.score = dict(score)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()
            self.segments = []
            self.recent_calls = []
            self.score = {}

    # ------------------------------------------------------------ readers (the ask service)

    def __len__(self) -> int:
        with self._lock:
            return len(self._samples)

    def track(self) -> Track:
        with self._lock:
            return Track(list(self._samples))

    def last_rally(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self.segments[-1]) if self.segments else None

    def rally(self, rally_no: int) -> dict[str, Any] | None:
        with self._lock:
            for s in self.segments:
                if int(s.get("rally_no", -1)) == rally_no:
                    return dict(s)
        return None

    def snapshot(self) -> dict[str, Any]:
        """Everything a question may need, read atomically."""
        with self._lock:
            return {
                "track": Track(list(self._samples)),
                "segments": [dict(s) for s in self.segments],
                "recent_calls": [dict(c) for c in self.recent_calls],
                "score": dict(self.score),
                "field": self.field,
                "sport": self.sport,
            }

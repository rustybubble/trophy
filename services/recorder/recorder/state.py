"""Non-blocking, read-only detection of engine-completed games in Spacetime."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor

from trophy.recordings import safe_id


class GameEndMonitor:
    def __init__(self, uri: str, module: str) -> None:
        self.uri, self.module = uri.rstrip("/"), safe_id(module)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recording-game-end")
        self.future: Future[set[str]] | None = None
        self.next_poll = 0.0
        self.ended: set[str] = set()
        self.token: str | None = None
        self.error: str | None = None

    def _query(self, game_ids: set[str]) -> set[str]:
        if self.token is None:
            request = urllib.request.Request(f"{self.uri}/v1/identity", data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=2) as response:
                self.token = json.load(response)["token"]
        ended = set()
        for game in sorted(game_ids):
            safe_id(game)
            request = urllib.request.Request(
                f"{self.uri}/v1/database/{self.module}/sql",
                data=f"SELECT * FROM game WHERE game_id = '{game}'".encode(),
                headers={"Content-Type": "text/plain", "Authorization": f"Bearer {self.token}"},
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                result = json.load(response)[0]
            names = [
                c["name"].get("some") if isinstance(c["name"], dict) else c["name"]
                for c in result["schema"]["elements"]
            ]
            for values in result["rows"]:
                row = dict(zip(names, values, strict=True))
                if row["status"] == "ended":
                    ended.add(game)
        return ended

    def check(self, game_ids: set[str]) -> set[str]:
        if self.future and self.future.done():
            try:
                self.ended.update(self.future.result())
                self.error = None
            except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
                self.error = type(exc).__name__  # no HTTP bodies, credentials or game contents in logs
            self.future = None
        now = time.monotonic()
        if game_ids and self.future is None and now >= self.next_poll:
            self.future = self.executor.submit(self._query, game_ids - self.ended)
            self.next_poll = now + 1
        return self.ended.copy()

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)

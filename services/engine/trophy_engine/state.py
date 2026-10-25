"""StateWriter: where the engine's layer-3 rows go. Spacetime for real, memory for tests and replay_test.

The Spacetime writer requires ``SPACETIME_ENGINE_TOKEN``: there is no silent no-op mode.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Protocol

from trophy.world import SpacetimeClient


class StateWriter(Protocol):
    def upsert_game(self, game: dict[str, Any]) -> None: ...
    def upsert_camera(self, cam: dict[str, Any]) -> None: ...
    def open_rally(self, rally: dict[str, Any]) -> None: ...
    def close_rally(self, rally: dict[str, Any]) -> None: ...
    def post_call(self, call: dict[str, Any]) -> None: ...
    def update_call_status(self, call_id: str, status: str, suggested: str | None = None) -> None: ...
    def set_score(self, rows: list[dict[str, Any]]) -> None: ...
    def open_challenge(self, ch: dict[str, Any]) -> None: ...
    def resolve_challenge(self, ch: dict[str, Any]) -> None: ...
    def post_ai_vote(self, vote: dict[str, Any]) -> None: ...
    def insert_house_rule(self, hr: dict[str, Any]) -> None: ...
    def set_house_rule_status(self, patch: dict[str, Any]) -> None: ...
    def post_ask(self, ask: dict[str, Any]) -> None: ...
    def upsert_moment(self, moment: dict[str, Any]) -> None: ...
    def set_best_play(self, game_id: str, moment_id: str, reasons: list[str]) -> None: ...
    def post_commentary(self, row: dict[str, Any]) -> None: ...


class MemoryState:
    """Keeps every row in dicts keyed like the Spacetime tables. Used by tests, replay_test and trophy-ctl --dry."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.log: list[tuple[str, dict[str, Any]]] = []

    def _put(self, table: str, key: str, row: dict[str, Any]) -> None:
        self.tables[table][key] = dict(row)
        self.log.append((table, dict(row)))

    def rows(self, table: str) -> list[dict[str, Any]]:
        return list(self.tables[table].values())

    def upsert_game(self, game: dict[str, Any]) -> None:
        self._put("game", game["game_id"], game)

    def upsert_camera(self, cam: dict[str, Any]) -> None:
        self._put("camera", cam["cam_id"], cam)

    def open_rally(self, rally: dict[str, Any]) -> None:
        self._put("rally", f"{rally['game_id']}:{rally['rally_no']}", rally)

    def close_rally(self, rally: dict[str, Any]) -> None:
        self._put("rally", f"{rally['game_id']}:{rally['rally_no']}", rally)

    def post_call(self, call: dict[str, Any]) -> None:
        self._put("call", call["id"], call)

    def update_call_status(self, call_id: str, status: str, suggested: str | None = None) -> None:
        row = dict(self.tables["call"].get(call_id) or {"id": call_id})
        row["status"] = status
        if suggested is not None:
            row["suggested"] = suggested
        self._put("call", call_id, row)

    def set_score(self, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            self._put("score", f"{r['game_id']}:{r['team_id']}", r)

    def open_challenge(self, ch: dict[str, Any]) -> None:
        self._put("challenge", ch["challenge_id"], ch)
        self.update_call_status(ch["call_id"], "challenged")  # the module does this too

    def resolve_challenge(self, ch: dict[str, Any]) -> None:
        self._put("challenge", ch["challenge_id"], ch)
        self.update_call_status(ch["call_id"], "upheld" if ch.get("result") == "upheld" else "overturned")

    def post_ai_vote(self, vote: dict[str, Any]) -> None:
        self._put("ai_vote", f"{vote['call_id']}:{vote['backend']}", vote)

    def insert_house_rule(self, hr: dict[str, Any]) -> None:
        self._put("house_rule", hr["rule_version"], hr)

    def set_house_rule_status(self, patch: dict[str, Any]) -> None:
        row = dict(self.tables["house_rule"].get(patch["rule_version"]) or {})
        row.update(patch)
        self._put("house_rule", patch["rule_version"], row)

    def post_ask(self, ask: dict[str, Any]) -> None:
        self._put("ask", ask["ask_id"], ask)

    def get_house_rule(self, rule_version: str) -> dict[str, Any] | None:
        row = self.tables["house_rule"].get(rule_version)
        return dict(row) if row else None

    def upsert_moment(self, moment: dict[str, Any]) -> None:
        self._put("moment", moment["moment_id"], moment)

    def set_best_play(self, game_id: str, moment_id: str, reasons: list[str]) -> None:
        for mid, m in list(self.tables["moment"].items()):
            if m.get("game_id") == game_id and m.get("is_best_play") and mid != moment_id:
                m["is_best_play"] = False
        m = self.tables["moment"].get(moment_id)
        if m is not None:
            m["is_best_play"] = True
            m["reasons"] = list(reasons)
        self.log.append(("set_best_play", {"game_id": game_id, "moment_id": moment_id, "reasons": list(reasons)}))

    def post_commentary(self, row: dict[str, Any]) -> None:
        self._put("commentary", f"{row['moment_id']}:{row['voice']}", row)


class SpacetimeState:
    """Writes through the module's reducers with the engine identity (one JSON-string argument each, D-25)."""

    def __init__(self, client: SpacetimeClient | None = None) -> None:
        if client is None:
            token = os.environ.get("SPACETIME_ENGINE_TOKEN", "")
            if not token:
                raise RuntimeError("SPACETIME_ENGINE_TOKEN is not set (run spacetime/scripts/provision.py)")
            client = SpacetimeClient(token=token)
        self.client = client

    def _call(self, reducer: str, payload: Any) -> None:
        self.client.call(reducer, json.dumps(payload))

    def upsert_game(self, game: dict[str, Any]) -> None:
        self._call("upsert_game", game)

    def upsert_camera(self, cam: dict[str, Any]) -> None:
        self._call("upsert_camera", cam)

    def open_rally(self, rally: dict[str, Any]) -> None:
        self._call("open_rally", rally)

    def close_rally(self, rally: dict[str, Any]) -> None:
        self._call("close_rally", rally)

    def post_call(self, call: dict[str, Any]) -> None:
        self._call("post_call", call)

    def update_call_status(self, call_id: str, status: str, suggested: str | None = None) -> None:
        patch: dict[str, Any] = {"call_id": call_id, "status": status}
        if suggested is not None:
            patch["suggested"] = suggested
        self._call("update_call_status", patch)

    def set_score(self, rows: list[dict[str, Any]]) -> None:
        self._call("set_score", rows)

    def open_challenge(self, ch: dict[str, Any]) -> None:
        self._call("open_challenge", ch)

    def resolve_challenge(self, ch: dict[str, Any]) -> None:
        self._call("resolve_challenge", ch)

    def post_ai_vote(self, vote: dict[str, Any]) -> None:
        self._call("post_ai_vote", vote)

    def insert_house_rule(self, hr: dict[str, Any]) -> None:
        self._call("insert_house_rule", hr)

    def set_house_rule_status(self, patch: dict[str, Any]) -> None:
        self._call("set_house_rule_status", patch)

    def post_ask(self, ask: dict[str, Any]) -> None:
        self._call("post_ask", ask)

    def get_house_rule(self, rule_version: str) -> dict[str, Any] | None:
        """Read the row back (the compiler wrote plan/diff/results/pack_path into it) through Spacetime's SQL API."""
        import urllib.request

        safe = rule_version.replace("'", "")
        req = urllib.request.Request(
            f"{self.client.uri}/v1/database/{self.client.module}/sql",
            data=f"SELECT * FROM house_rule WHERE rule_version = '{safe}'".encode(),
            method="POST",
            headers={"Content-Type": "text/plain", "Authorization": f"Bearer {self.client.token}"},
        )
        with urllib.request.urlopen(req, timeout=self.client.timeout_s) as resp:
            data = json.loads(resp.read().decode("utf8"))
        rows = data[0].get("rows") if isinstance(data, list) and data else None
        if not rows:
            return None
        schema = [c.get("name") for c in data[0].get("schema", {}).get("elements", [])]
        row = dict(zip(schema, rows[0], strict=False)) if schema else {}
        js = row.get("json")
        return json.loads(js) if isinstance(js, str) else row or None

    def upsert_moment(self, moment: dict[str, Any]) -> None:
        self._call("upsert_moment", moment)  # reducer requested from Agent 1 (interfaces §11)

    def set_best_play(self, game_id: str, moment_id: str, reasons: list[str]) -> None:
        self._call("set_best_play", {"game_id": game_id, "moment_id": moment_id, "reasons": reasons})

    def post_commentary(self, row: dict[str, Any]) -> None:
        self._call("post_commentary", row)

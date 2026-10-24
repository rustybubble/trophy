"""Local integration smoke checks. All inserted game metadata is labelled synthetic."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def check_platform(env: dict[str, str]) -> None:
    uri = env.get("SPACETIME_URI", "http://127.0.0.1:3000").rstrip("/")
    module = env.get("SPACETIME_MODULE", "trophy")
    ident = f"synthetic-platform-{time.time_ns()}"

    def call(name: str, payload: dict, role: str = "engine", rejected: bool = False) -> None:
        req = urllib.request.Request(
            f"{uri}/v1/database/{module}/call/{name}",
            data=json.dumps([json.dumps(payload)]).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {env[f'SPACETIME_{role.upper()}_TOKEN']}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                if rejected:
                    raise AssertionError(f"{name} unexpectedly allowed {role}")
        except urllib.error.HTTPError as exc:
            if not rejected or exc.code != 530:
                raise RuntimeError(f"{name} failed: HTTP {exc.code}") from None

    moment = {
        "moment_id": ident,
        "game_id": ident,
        "kind": "bookmark",
        "t_game_s": 1,
        "t_start_s": 0,
        "t_end_s": 2,
        "label": "SYNTHETIC platform smoke",
        "score_after": "0–0",
        "tags": ["synthetic"],
        "reasons": [],
        "highlight_score": 0.1,
        "is_best_play": False,
        "thumb_t_s": 1,
    }
    call("upsert_moment", moment)
    call("set_best_play", {"game_id": ident, "moment_id": ident, "reasons": ["synthetic smoke"]})
    for voice in ("pbp", "colour"):
        call(
            "post_commentary",
            {
                "moment_id": ident,
                "game_id": ident,
                "voice": voice,
                "text": "Synthetic test",
                "facts": {},
                "validated": True,
                "source": "template",
                "created_at_ms": 1,
            },
        )
    run = {
        "schema": "trophy.droid_run.v1",
        "run_id": ident,
        "sport": "synthetic",
        "kind": "compile",
        "trigger": {"source": "cli"},
        "status": "ready",
        "backend": "droid",
        "model": "synthetic",
        "attempt": 1,
        "max_attempts": 1,
        "plan_md": "Synthetic test",
        "steps": [],
        "diff": "",
        "results": {"passed": True, "tests": [], "calls_changed": [], "engine": "synthetic", "summary": "smoke"},
        "commit": ident,
        "started_at_ms": 1,
        "updated_at_ms": 2,
    }
    call("update_droid_run", run, "compiler")
    call("set_droid_run_status", {"run_id": ident, "status": "approved"}, "compiler", rejected=True)
    call("set_droid_run_status", {"run_id": ident, "status": "approved"})
    call(
        "upsert_sport_module",
        {
            "sport": "synthetic",
            "game_id": ident,
            "version": 1,
            "backend": "handwritten",
            "run_id": ident,
            "path": "synthetic/no-code",
            "commit": ident,
            "approved_at_ms": 1,
        },
    )
    for reducer in ("upsert_moment", "set_best_play", "post_commentary", "set_droid_run_status", "upsert_sport_module"):
        call(reducer, {}, "vision", rejected=True)
    call("update_droid_run", {}, "engine", rejected=True)
    call("update_droid_run", run, "compiler", rejected=True)
    req = urllib.request.Request(
        f"{uri}/v1/database/{module}/sql",
        data=f"SELECT * FROM commentary WHERE game_id = '{ident}'".encode(),
        headers={"Content-Type": "text/plain", "Authorization": f"Bearer {env['SPACETIME_ENGINE_TOKEN']}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert len(json.load(resp)[0]["rows"]) == 2, "both voices must survive"
    print("platform check: 7 successful writes, 8 rejected writes, both commentary voices retained (synthetic)")

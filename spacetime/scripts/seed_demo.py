"""Replay a labelled-synthetic MockScript into the live Spacetime module through the real reducers, with
each writer's own token (engine / vision / compiler). Doubles as the module's smoke test.

    python spacetime/scripts/seed_demo.py                         # table-tennis demo into a new game, no delays
    python spacetime/scripts/seed_demo.py --speed 1 --game g_xxxxxxxx
    python spacetime/scripts/seed_demo.py --check                 # also assert row counts + auth rejections

Seeded games carry params.synthetic = true so UIs can label them. Needs provision.py to have run.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "packages" / "state-client" / "fixtures"
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


def read_env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


ENV = read_env()
URI = (ENV.get("SPACETIME_URI") or "http://127.0.0.1:3000").rstrip("/")
MODULE = ENV.get("SPACETIME_MODULE") or "trophy"
TOKENS = {r: ENV.get(f"SPACETIME_{r.upper()}_TOKEN", "") for r in ("engine", "vision", "compiler")}


def call(reducer: str, payload: object, role: str | None) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{URI}/v1/database/{MODULE}/call/{reducer}",
        data=json.dumps([json.dumps(payload)]).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    if role:
        req.add_header("Authorization", f"Bearer {TOKENS[role]}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def must(reducer: str, payload: object, role: str) -> None:
    code, body = call(reducer, payload, role)
    if code != 200:
        raise SystemExit(f"{reducer} as {role}: HTTP {code}: {body[:300]}")


def sql(query: str) -> list[dict]:
    req = urllib.request.Request(
        f"{URI}/v1/database/{MODULE}/sql",
        data=query.encode(),
        method="POST",
        headers={"Authorization": f"Bearer {TOKENS['engine']}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        res = json.loads(r.read())[0]
    names = [e["name"]["some"] for e in res["schema"]["elements"]]
    return [dict(zip(names, row, strict=True)) for row in res["rows"]]


def seed(script: dict, game_id: str, speed: float, run_tag: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    seen_hr: set[str] = set()
    t_start = time.monotonic()
    for step in sorted(script["steps"], key=lambda s: s["at_ms"]):
        if speed > 0:
            delay = step["at_ms"] / 1000 / speed - (time.monotonic() - t_start)
            if delay > 0:
                time.sleep(delay)
        table = step["table"]
        # fresh ids per run (the fixture's ids all start with 01JDEM), so seeding can be repeated
        row = json.loads(json.dumps(step["row"]).replace("01JDEM", "01J" + run_tag))
        if "game_id" in row:
            row["game_id"] = game_id
        if table == "game":
            row["params"] = {**row.get("params", {}), "synthetic": True, "label": script["label"]}
            must("upsert_game", row, "engine")
        elif table == "camera":
            must("upsert_camera", row, "engine")
        elif table == "rally":
            must("open_rally" if row["status"] == "open" else "close_rally", row, "engine")
        elif table == "call":
            must("post_call", row, "engine")
        elif table == "score":
            must("set_score", [row], "engine")
        elif table == "challenge":
            must("open_challenge" if row["status"] == "open" else "resolve_challenge", row, "engine")
        elif table == "ai_vote":
            must("post_ai_vote", row, "engine")
        elif table == "ask":
            must("post_ask", row, "engine")
        elif table == "moment":
            must("upsert_moment", row, "engine")
        elif table == "commentary":
            must("post_commentary", row, "engine")
        elif table == "observation":
            must("post_observations", [row], "vision")
        elif table == "track_sample":
            must("post_track_samples", [row], "vision")
        elif table == "house_rule":
            rv = row["rule_version"]
            if rv not in seen_hr:
                must("insert_house_rule", row, "engine")
                seen_hr.add(rv)
            elif row["status"] in ("compiling", "ready", "failed"):
                patch = {
                    k: row[k] for k in ("rule_version", "status", "plan_md", "steps", "diff", "results", "pack_path")
                }
                must("update_house_rule_progress", patch, "compiler")
            else:
                must("set_house_rule_status", {"rule_version": rv, "status": row["status"]}, "engine")
        else:
            raise SystemExit(f"unknown table {table}")
        counts[table] = counts.get(table, 0) + 1
    return counts


def check(game_id: str) -> None:
    g = f"game_id = '{game_id}'"
    expect = {
        "call": 4,
        "score": 2,
        "rally": 3,
        "challenge": 1,
        "ai_vote": 3,
        "house_rule": 1,
        "ask": 2,
        "camera": 1,
        "moment": 4,
        "commentary": 2,
    }
    for table, n in expect.items():
        got = len(sql(f"SELECT * FROM {table} WHERE {g}"))
        assert got == n, f"{table}: expected {n} rows, got {got}"
    calls = {r["rule_id"]: r for r in sql(f"SELECT * FROM call WHERE {g}")}
    assert calls["edge_ball"]["status"] == "upheld", calls["edge_ball"]["status"]
    votes = sql(f"SELECT * FROM ai_vote WHERE {g}")
    assert all(v["challenge_id"] for v in votes), "speculative votes should be linked to the challenge"
    hr = sql(f"SELECT * FROM house_rule WHERE {g}")[0]
    assert hr["status"] == "approved" and json.loads(hr["json"])["diff"], hr["status"]
    b = {r["team_id"]: r["points"] for r in sql(f"SELECT * FROM score WHERE {g}")}
    assert b == {"A": 0, "B": 3}, b
    best = [m for m in sql(f"SELECT * FROM moment WHERE {g}") if m["is_best_play"]]
    assert len(best) == 1, f"expected one best play, got {len(best)}"
    assert len(sql(f"SELECT * FROM observation WHERE {g}")) > 5
    assert len(sql(f"SELECT * FROM track_sample WHERE {g}")) > 20
    # auth: wrong role, no token, compiler can't approve, engine can't post observations
    obs = sql(f"SELECT * FROM observation WHERE {g}")[0]
    for reducer, payload, role in [
        ("post_call", json.loads(sql(f"SELECT * FROM call WHERE {g}")[0]["json"]), "vision"),
        ("post_call", json.loads(sql(f"SELECT * FROM call WHERE {g}")[0]["json"]), None),
        ("post_observations", [json.loads(obs["json"])], "engine"),
        ("update_house_rule_progress", {"rule_version": hr["rule_version"], "status": "compiling"}, "compiler"),
        ("register_service", {"identity_hex": "00" * 32, "role": "engine"}, "engine"),
    ]:
        code, body = call(reducer, payload, role)
        assert code == 530, f"{reducer} as {role or 'anonymous'} should be rejected, got {code} {body[:120]}"
    code, _ = call("post_call", {"id": "x"}, "engine")
    assert code == 530, "missing fields should be rejected"
    print("check: row counts, statuses, vote linking, scores, and 6 rejections all as expected")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="table-tennis-demo.json")
    ap.add_argument("--game", default=None, help="game_id to seed into (default: a new random one)")
    ap.add_argument("--speed", type=float, default=0, help="0 = no delays; 1 = real time")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not all(TOKENS.values()):
        raise SystemExit("run spacetime/scripts/provision.py first")
    script = json.loads((FIXTURES / a.fixture).read_text("utf8"))
    game_id = a.game or "g_" + "".join(secrets.choice(CROCKFORD) for _ in range(8))
    run_tag = "".join(secrets.choice(CROCKFORD.upper()) for _ in range(3))
    t0 = time.perf_counter()
    counts = seed(script, game_id, a.speed, run_tag)
    dt = time.perf_counter() - t0
    print(f"seeded {game_id} ({script['label'][:40]}…): {sum(counts.values())} reducer calls in {dt:.2f} s: {counts}")
    if a.check:
        check(game_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())

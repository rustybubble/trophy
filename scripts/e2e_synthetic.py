"""`make e2e-synthetic`: the headless demo check on the SYNTHETIC fixtures, against the running stack.

    python3 scripts/e2e_synthetic.py             # needs redis, spacetime (provisioned), gateway, engine, compiler
    python3 scripts/e2e_synthetic.py --no-droid  # skip the Factory Droid house rule (no key / no spend wanted)

1. creates a game through the gateway (as a phone would), 2. replays the labelled-SYNTHETIC fixtures into the live
engine with `trophy-play`, 3. checks the calls, rallies and score in Spacetime against the fixture labels, 4. submits a
house rule, waits for the Droid run to reach `ready`, approves it and checks the engine hot-loaded it. Prints measured
wall times. Exit 0 only when every check passes. Nothing here is a real-footage measurement.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOUSE_RULE = "no lets: a serve that clips the net is played on"


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split(" #")[0].strip()
    return out


E = env()
GATEWAY = f"http://127.0.0.1:{8000 + int(E.get('PORT_OFFSET') or 0)}"
STDB = (E.get("SPACETIME_URI") or "http://127.0.0.1:3000").rstrip("/")
MODULE = E.get("SPACETIME_MODULE") or "trophy"


def http(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


def sql(query: str) -> list[dict]:
    """Rows as dicts (Spacetime 2.13 names columns as options; 2.10 as strings)."""
    body = json.loads(
        http(
            f"{STDB}/v1/database/{MODULE}/sql",
            query.encode(),
            {"Content-Type": "text/plain", "Authorization": f"Bearer {E['SPACETIME_ENGINE_TOKEN']}"},
        )
    )
    if not body:
        return []
    names = []
    for i, col in enumerate(body[0].get("schema", {}).get("elements", [])):
        n = col.get("name")
        n = n.get("some") if isinstance(n, dict) else n
        names.append(str(n) if n else f"col{i}")
    return [dict(zip(names, row, strict=False)) for row in body[0].get("rows", [])]


def ctl(cmd: str, game_id: str, args: dict) -> None:
    subprocess.run(
        [
            "uv",
            "run",
            "--directory",
            str(ROOT / "services/engine"),
            "--frozen",
            "trophy-ctl",
            cmd,
            game_id,
            "--args",
            json.dumps(args),
            "--by",
            "judge",
        ],
        check=True,
        capture_output=True,
    )


def wait_for(pred, timeout_s: float, every_s: float = 0.5):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        v = pred()
        if v:
            return v, time.monotonic() - t0
        time.sleep(every_s)
    return None, time.monotonic() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-droid", action="store_true")
    ap.add_argument("--speed", type=float, default=4.0)
    a = ap.parse_args()
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        ok &= bool(cond)
        print(("  ok   " if cond else "  FAIL ") + msg)

    print(f"gateway {GATEWAY}: {json.loads(http(f'{GATEWAY}/api/healthz'))}")
    game = json.loads(
        http(
            f"{GATEWAY}/api/games",
            json.dumps({"sport": "table_tennis", "params": {"synthetic": True, "label": "SYNTHETIC e2e"}}).encode(),
            {"Content-Type": "application/json"},
        )
    )
    gid = game["game_id"]
    print(f"game {gid} created through the gateway")
    time.sleep(0.5)

    t0 = time.monotonic()
    subprocess.run(
        [
            "uv",
            "run",
            "--directory",
            str(ROOT / "services/engine"),
            "--frozen",
            "trophy-play",
            "--game",
            gid,
            "--speed",
            str(a.speed),
        ],
        check=True,
        capture_output=True,
    )
    play_s = time.monotonic() - t0
    fixtures = ROOT / "evals/fixtures/synthetic/table_tennis"
    labels = [json.loads(p.read_text()) for p in sorted(fixtures.glob("*.labels.json"))]
    want = [lab["rally_winner"] for lab in labels]
    q_points = f"SELECT * FROM call WHERE game_id = '{gid}' AND kind = 'point'"
    wait_for(lambda: len(sql(q_points)) >= len(want), 15)
    points = sorted(sql(q_points), key=lambda r: r["rally_no"])
    got = [r["team_id"] for r in points]
    print(f"replayed {len(labels)} fixtures in {play_s:.1f} s at x{a.speed}")
    check(got == want, f"point calls per fixture {got} match the labelled rally winners {want}")
    scores = {r["team_id"]: r["points"] for r in sql(f"SELECT * FROM score WHERE game_id = '{gid}'")}
    check(scores == {t: want.count(t) for t in ("A", "B")}, f"score {scores}")
    rallies = sql(f"SELECT * FROM rally WHERE game_id = '{gid}' AND status = 'closed'")
    check(len(rallies) == len(want), f"{len(rallies)} rallies closed")
    moments = sql(f"SELECT * FROM moment WHERE game_id = '{gid}'")
    check(len(moments) >= len(want), f"{len(moments)} moments written")

    if not a.no_droid:
        t0 = time.monotonic()
        ctl("submit_house_rule", gid, {"text": HOUSE_RULE, "source": "typed"})
        q_rule = f"SELECT * FROM house_rule WHERE game_id = '{gid}'"
        row, _ = wait_for(lambda: next(iter(sql(q_rule)), None), 10)
        check(row is not None and row["status"] in ("pending", "compiling"), f"house rule pending: {HOUSE_RULE!r}")
        rv = row["rule_version"] if row else ""
        q_rv = f"SELECT * FROM house_rule WHERE rule_version = '{rv}'"

        def status_in(*states: str):
            return lambda: next((r for r in sql(q_rv) if r["status"] in states), None)

        row, _ = wait_for(status_in("ready", "failed"), 150)
        status = row["status"] if row else "timeout"
        js = json.loads(row["json"]) if row else {}
        res = js.get("results") or {}
        print(f"Droid run: {status} after {time.monotonic() - t0:.1f} s; gate {res.get('summary', '')!r}")
        check(status == "ready", "Droid run reached ready")
        if status == "ready":
            t1 = time.monotonic()
            ctl("approve_house_rule", gid, {"rule_version": rv})
            row, _ = wait_for(status_in("approved", "failed"), 15)
            st = row["status"] if row else "timeout"
            err = (json.loads(row["json"]).get("error") if row else None) or ""
            check(st == "approved", f"approved + hot-loaded by the engine in {time.monotonic() - t1:.1f} s {err}")

    print("E2E PASS" if ok else "E2E FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

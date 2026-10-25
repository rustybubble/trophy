"""`make e2e` (checkpoint C2): play the CC BY ping-pong clip into the running stack as a phone and check every hop.

    make dev                       # in another terminal: redis, spacetime, gateway, recorder (+ flight, engine)
    make e2e                       # = uv run --project services/gateway python scripts/e2e.py
    python scripts/e2e.py --require-calls   # fail unless flight + engine produced observations and calls
    make e2e-calls                 # = --calls-hop: also run hop 5 (once flight + engine are on main)

Hops checked:
  1. stack health: gateway /api/healthz (redis, spacetime, recorder);
  2. frame bus: the clip streamed at 1280x720 30 fps reaches `frames:{cam}` at >= 27 fps;
  3. recorder + replay: HLS, a replay clip, voter crops < 1 MB, the Watch manifest and tracks (clip_as_phone
     --check-replay, on a hand-posted TEST call it labels as such);
  4. Spacetime: observations (flight) and calls (engine) for the game, excluding that TEST call;
  5. calls (`--calls-hop`, or TROPHY_E2E_CALLS=1; implies --require-calls): every call matches the contract, obeys
     the confidence gate, agrees with its closed rally and the score table, and posts within 1.5 s p50
     (scripts/e2e_calls.py). The clip is unlabelled, so hop 5 checks consistency, not accuracy.
Hops 4-5 need Agent 2's flight and Agent 3's engine. Without them hop 4 reports PENDING rather than passing, hop 5
is SKIPPED unless asked for, and C2 is not met. The report goes to data/local/e2e/<game>.json. The clip is CC BY
(data/clips/credits.json) and stays local.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import redis
from e2e_calls import check_calls

ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "data" / "local" / "clips" / "table_tennis" / "7maQFqJ3XQ0.mp4"  # tools/fetch_clips.py
# 8:30-9:00 of the club match: rallies plus the disputed edge ball at 8:36 (docs/plan/clip-library.md)
START_S, SECONDS = 510.0, 30.0
EDGE_BALL_S = 516.0  # 8:36 in the source video


def env() -> dict[str, str]:
    out = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split("#")[0].strip()
    return out


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def sql(stdb: str, module: str, token: str, query: str) -> list[dict]:
    req = urllib.request.Request(
        f"{stdb}/v1/database/{module}/sql",
        data=query.encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())[0]
    names = [c["name"].get("some") if isinstance(c["name"], dict) else c["name"] for c in result["schema"]["elements"]]
    return [dict(zip(names, row, strict=True)) for row in result["rows"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", type=Path, default=CLIP)
    ap.add_argument("--start", type=float, default=START_S)
    ap.add_argument("--seconds", type=float, default=SECONDS)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--stdb", default="http://127.0.0.1:3000")
    ap.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    ap.add_argument("--require-calls", action="store_true", help="fail (not PENDING) without observations + calls")
    ap.add_argument(
        "--calls-hop",
        action="store_true",
        default=os.environ.get("TROPHY_E2E_CALLS") == "1",
        help="hop 5: check the calls themselves (contract, gate, scoring, latency); implies --require-calls",
    )
    a = ap.parse_args()
    a.require_calls = a.require_calls or a.calls_hop
    e = env()
    module = e.get("SPACETIME_MODULE") or "trophy"
    checks: dict[str, dict] = {}

    def check(name: str, ok: bool | None, **detail) -> None:
        checks[name] = {"status": "PASS" if ok else ("PENDING" if ok is None else "FAIL"), **detail}
        print(f"{checks[name]['status']:<8} {name} {json.dumps(detail)}")

    def skip(name: str, why: str) -> None:
        checks[name] = {"status": "SKIPPED", "note": why}
        print(f"{'SKIPPED':<8} {name} {why}")

    if not a.clip.exists():
        print(f"missing clip {a.clip}: run `python tools/fetch_clips.py --sport table_tennis` first", file=sys.stderr)
        return 2

    health = get_json(f"{a.base}/api/healthz")
    check("stack health", all(health.get(k) for k in ("redis", "spacetime", "recorder")), healthz=health)
    if checks["stack health"]["status"] == "FAIL":
        print("start the stack first: make dev (redis, spacetime, gateway, recorder)", file=sys.stderr)
        return 1

    report_dir = ROOT / "data" / "local" / "e2e"
    report_dir.mkdir(parents=True, exist_ok=True)
    tmp = report_dir / f"clip-{int(time.time())}.json"
    cmd = [
        sys.executable,
        str(ROOT / "services" / "gateway" / "scripts" / "clip_as_phone.py"),
        str(a.clip),
        "--start",
        str(a.start),
        "--seconds",
        str(a.seconds),
        "--base",
        a.base,
        "--stdb",
        a.stdb,
        "--module",
        module,
        "--redis-url",
        a.redis_url,
        "--check-replay",
        "--report",
        str(tmp),
    ]
    t0 = time.time()
    run = subprocess.run(cmd, capture_output=True, text=True)
    print(run.stdout.strip())
    if run.returncode != 0:
        check("stream + replay", False, stderr=run.stderr.strip().splitlines()[-5:])
        return 1
    rep = json.loads(tmp.read_text("utf8"))
    tmp.unlink()
    gid, cam, test_call = rep["game_id"], rep["cam_id"], rep["call_id"]

    rows = redis.Redis.from_url(a.redis_url).xrange(f"frames:{cam}")
    tsrv = [float(f[b"t_srv_ms"]) for _, f in rows]
    span = (tsrv[-1] - tsrv[0]) / 1000 if len(tsrv) > 1 else 0
    fps = (len(rows) - 1) / span if span else 0.0
    size = f"{rows[-1][1][b'w'].decode()}x{rows[-1][1][b'h'].decode()}" if rows else "?"
    # the bus keeps the newest 300 frames (~10 s), so fps is measured over that window
    check("frame bus", fps >= 27 and size == "1280x720", fps=round(fps, 1), size=size, frames_sent=rep["frames_sent"])
    replay = rep.get("replay") or {}
    check(
        "recorder + replay",
        bool(replay) and replay.get("hls_playlist") == 200 and replay.get("crop_frames", 0) >= 1,
        **replay,
    )

    token = e.get("SPACETIME_ENGINE_TOKEN", "")
    time.sleep(2)  # let flight/engine flush the tail of the clip
    obs = sql(a.stdb, module, token, f"SELECT * FROM observation WHERE game_id = '{gid}'")
    calls = sql(a.stdb, module, token, f"SELECT * FROM call WHERE game_id = '{gid}'")
    calls = [c for c in calls if c["call_id"] != test_call]
    kinds = sorted({json.loads(o["json"])["type"] for o in obs})
    have = bool(obs) and bool(calls)
    check(
        "observations + calls in Spacetime",
        True if have else (False if a.require_calls else None),
        observations=len(obs),
        observation_types=kinds,
        calls=len(calls),
        note="" if have else "needs flight (Agent 2) and the engine (Agent 3) running; C2 is not met until this passes",
    )

    if not a.calls_hop:
        skip("calls (hop 5)", "off until flight + engine are on main: make e2e-calls (or --calls-hop) turns it on")
    else:
        games = sql(a.stdb, module, token, f"SELECT * FROM game WHERE game_id = '{gid}'")
        rallies = sql(a.stdb, module, token, f"SELECT * FROM rally WHERE game_id = '{gid}'")
        scores = sql(a.stdb, module, token, f"SELECT * FROM score WHERE game_id = '{gid}'")
        # the clip's 0 s is a moment after the game's t0 (the game is created first), so this window is approximate
        edge = EDGE_BALL_S - a.start
        window = (edge - 2.0, edge + 4.0) if a.start <= EDGE_BALL_S <= a.start + a.seconds else None
        for name, ok, detail in check_calls(
            json.loads(games[0]["json"]) if games else {},
            [json.loads(c["json"]) for c in calls],
            [json.loads(r["json"]) for r in rallies],
            [json.loads(s["json"]) for s in scores],
            edge_window_s=window,
        ):
            check(f"calls (hop 5): {name}", ok, **detail)

    out = {
        "schema": "trophy.e2e.v1",
        "game_id": gid,
        "cam_id": cam,
        "clip": a.clip.name,
        "clip_license": "CC BY (data/clips/credits.json)",
        "window_s": [a.start, a.start + a.seconds],
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "wall_s": round(time.time() - t0, 1),
        "checks": checks,
    }
    path = report_dir / f"{gid}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", "utf8")
    statuses = {c["status"] for c in checks.values()}
    verdict = "FAIL" if "FAIL" in statuses else ("PENDING" if "PENDING" in statuses else "PASS")
    print(f"e2e {verdict}: report {path.relative_to(ROOT)}")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())

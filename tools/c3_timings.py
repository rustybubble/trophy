"""C3 timings: how fast the live referee is, measured from one game's rows and logs (run on the Mac after a live game).

    uv run --project packages/py-trophy python tools/c3_timings.py --game g_xxxxxxxx
    uv run --project packages/py-trophy python tools/c3_timings.py --game latest --log data/local/logs/dev.log
    uv run --project packages/py-trophy python tools/c3_timings.py --snapshot data/local/c3/g_xxxxxxxx.rows.json

Sources (all local to the Mac; nothing secret is read: public tables are read with an anonymous identity):
  - Spacetime rows for the game: game, rally, call, challenge, ai_vote, house_rule, droid_run, ask;
  - the gateway's call acks, `<data-dir>/logs/call_ack.jsonl` (one row per phone that showed the call);
  - the phone-recorded challenge clips' metadata, `<data-dir>/clips/<game>/<call_id>/*.json` (`uploaded_at_ms`);
  - optionally `make dev` output (`--log`, e.g. `make dev 2>&1 | tee data/local/logs/dev.log`): the engine's
    `{"msg": "call", "ms": ...}` lines, its per-event processing time.

Every metric prints n, p50, p95 and max, and "not measured" when it has no rows. Calls with `p_source: manual`
(the e2e's hand-posted TEST call, judge adjustments) are excluded. A game with `params.synthetic` is labelled
SYNTHETIC in the output and the report: its numbers are not live measurements.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("game", "rally", "call", "challenge", "ai_vote", "house_rule", "droid_run", "ask")

# C3 targets (docs/plan/three-agent-plan.md §5, docs/plan/prompts/agent-1.md)
TARGET_SPOKEN_MS = 1500.0  # the call spoken <= 1.5 s after the rally ends (p50)
TARGET_REPLAY_MS = 4000.0  # challenge -> replay <= 4 s
TARGET_DROID_MS = 90_000.0  # the Droid rule end to end < 90 s
TARGET_ASK_MS = 3000.0  # voice ask -> answer starts <= 3 s

Rows = Mapping[str, list[dict[str, Any]]]


def percentile(xs: list[float], q: float) -> float:
    """Linear interpolation between closest ranks (numpy's default), q in [0, 100]."""
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def metric(name: str, xs: Iterable[float], target_ms: float | None = None, note: str = "") -> dict[str, Any]:
    v = [float(x) for x in xs]
    m: dict[str, Any] = {"name": name, "n": len(v), "target_ms": target_ms, "note": note}
    if not v:
        return {**m, "p50_ms": None, "p95_ms": None, "max_ms": None, "verdict": "not measured"}
    p50 = percentile(v, 50)
    m.update(p50_ms=round(p50, 1), p95_ms=round(percentile(v, 95), 1), max_ms=round(max(v), 1))
    m["verdict"] = "—" if target_ms is None else ("meets" if p50 <= target_ms else "misses")
    return m


def _engine_calls(rows: Rows) -> list[dict[str, Any]]:
    return [c for c in rows.get("call", []) if c.get("p_source") != "manual"]


def compute(
    rows: Rows,
    acks: Iterable[Mapping[str, Any]] = (),
    clips: Iterable[Mapping[str, Any]] = (),
    log_lines: Iterable[str] = (),
) -> dict[str, Any]:
    """All C3 timing metrics for one game. ``rows`` maps table name -> contract objects (each row's ``json``)."""
    game = (rows.get("game") or [{}])[0]
    gid = game.get("game_id")
    t0 = float(game.get("t0_ms") or 0.0)
    calls = _engine_calls(rows)
    by_id = {c["id"]: c for c in calls}
    rallies = {int(r["rally_no"]): r for r in rows.get("rally", []) if r.get("rally_no") is not None}

    def game_ms(t_s: float) -> float:
        return t0 + 1000.0 * float(t_s)

    # 1. rally end -> call posted -> call_ack on the first phone
    first_ack: dict[str, float] = {}
    for a in acks:
        if a.get("game_id", gid) != gid or a.get("call_id") not in by_id or a.get("t_ack_srv_ms") is None:
            continue
        cid = a["call_id"]
        first_ack[cid] = min(first_ack.get(cid, float("inf")), float(a["t_ack_srv_ms"]))
    ends = []  # (call, rally end in server ms) for the calls that ended a rally
    for c in calls:
        if not (c.get("points") or c.get("outcome") == "let"):
            continue
        r = rallies.get(int(c.get("rally_no") or 0)) or {}
        t_end = r.get("t_end_s") if r.get("t_end_s") is not None else c.get("t_game_s")
        if t0 and t_end is not None:
            ends.append((c, game_ms(t_end)))
    out: list[dict[str, Any]] = [
        metric(
            "event -> call posted (every engine call)",
            (float(c["created_at_ms"]) - game_ms(c["t_game_s"]) for c in calls if t0),
            note="the triggering event's game time -> the call row's created_at_ms",
        ),
        metric("rally end -> scoring call posted", (float(c["created_at_ms"]) - t for c, t in ends)),
        metric(
            "call posted -> shown on the first phone (call_ack)",
            (first_ack[c["id"]] - float(c["created_at_ms"]) for c in calls if c["id"] in first_ack),
        ),
        metric(
            "rally end -> shown on the first phone (C3 spoken-call target)",
            (first_ack[c["id"]] - t for c, t in ends if c["id"] in first_ack),
            TARGET_SPOKEN_MS,
            note="call_ack is sent when the banner shows; speech starts one TTS first chunk later, which is not "
            "logged (iPhone: 112 ms after the request, single run), so this is a lower bound on 'spoken'",
        ),
    ]

    # 2. challenge -> replay ready (the first phone-recorded clip of the challenged call uploaded)
    uploaded: dict[str, float] = {}
    for m in clips:
        if m.get("call_id") in by_id and m.get("uploaded_at_ms") is not None:
            cid = m["call_id"]
            uploaded[cid] = min(uploaded.get(cid, float("inf")), float(m["uploaded_at_ms"]))
    chal = [h for h in rows.get("challenge", []) if h.get("call_id") in by_id]
    out.append(
        metric(
            "challenge -> replay ready (first clip uploaded)",
            (uploaded[h["call_id"]] - float(h["created_at_ms"]) for h in chal if h["call_id"] in uploaded),
            TARGET_REPLAY_MS,
            note=f"{sum(h['call_id'] not in uploaded for h in chal)} of {len(chal)} challenges had no clip",
        )
    )

    # 3. BETA call -> each ai_vote; votes must never delay the call
    votes = [v for v in rows.get("ai_vote", []) if v.get("call_id") in by_id and v.get("backend") != "geometry"]
    beta = {c["id"] for c in calls if c.get("tier") == "BETA"}
    early = [v for v in votes if float(v["created_at_ms"]) < float(by_id[v["call_id"]]["created_at_ms"])]
    for backend in sorted({v["backend"] for v in votes} | {"claude"}):
        out.append(
            metric(
                f"BETA call posted -> {backend} vote row",
                (
                    float(v["created_at_ms"]) - float(by_id[v["call_id"]]["created_at_ms"])
                    for v in votes
                    if v["backend"] == backend and v["call_id"] in beta and not v.get("error")
                ),
                note="uncalibrated vote probabilities; errored votes excluded",
            )
        )
    voted = {v["call_id"] for v in votes}
    out.append(
        metric(
            "votes never delayed a call: votes created before their call",
            (float(by_id[v["call_id"]]["created_at_ms"]) - float(v["created_at_ms"]) for v in early),
            note="PASS when n = 0: every vote row is newer than its call row",
        )
        | {"verdict": "PASS" if not early and votes else ("FAIL" if early else "not measured")}
    )
    out.append(
        metric(
            "event -> BETA call posted, calls that got votes",
            (float(by_id[c]["created_at_ms"]) - game_ms(by_id[c]["t_game_s"]) for c in beta & voted if t0),
            note="compare with 'event -> call posted': votes run in the background, so these should match",
        )
    )

    # 4. house rule: pending -> ready (the Droid) -> approved (the judge)
    runs = {
        (d.get("trigger") or {}).get("rule_version"): d
        for d in rows.get("droid_run", [])
        if (d.get("trigger") or {}).get("source") == "house_rule" and d.get("status") in ("ready", "approved")
    }
    p2r, r2a, p2a = [], [], []
    for h in rows.get("house_rule", []):
        run = runs.get(h.get("rule_version"))
        ready = run.get("finished_at_ms") if run else None
        if ready is not None:
            p2r.append(float(ready) - float(h["created_at_ms"]))
        if h.get("status") == "approved":
            p2a.append(float(h["updated_at_ms"]) - float(h["created_at_ms"]))
            if ready is not None:
                r2a.append(float(h["updated_at_ms"]) - float(ready))
    out += [
        metric("house rule pending -> ready (Droid: plan, edit, gate)", p2r),
        metric("house rule ready -> approved (the judge's click)", r2a, note="human time"),
        metric(
            "house rule pending -> approved and hot-loaded",
            p2a,
            TARGET_DROID_MS,
            note="includes the judge; 'approved' is the row's last update (updated_at_ms)",
        ),
    ]

    # 5. ask -> answer
    asks = [a for a in rows.get("ask", []) if a.get("kind") != "pending"]
    out.append(
        metric(
            "ask -> answer returned (gateway /api/ask round trip)",
            (float(a["latency_ms"]) for a in asks),
            TARGET_ASK_MS,
            note="excludes push-to-talk STT (Ink-2 turn.end, iPhone <= 82 ms) and the TTS first chunk; "
            f"{sum(a.get('kind') == 'pending' for a in rows.get('ask', []))} pending (Droid-written) answers excluded",
        )
    )

    # engine processing per event, from `make dev` output
    eng = []
    for line in log_lines:
        m = re.search(r"\{.*\}", line)
        if not m:
            continue
        try:
            j = json.loads(m.group(0))
        except ValueError:
            continue
        if j.get("svc") == "engine" and j.get("msg") == "call" and j.get("game_id") == gid and "ms" in j:
            eng.append(float(j["ms"]))
    out.append(metric("engine: event -> calls computed (log)", eng, note="from the engine's log lines"))

    synthetic = bool((game.get("params") or {}).get("synthetic"))
    return {
        "schema": "trophy.c3_timings.v1",
        "game_id": gid,
        "synthetic": synthetic,
        "label": "SYNTHETIC: not a live measurement" if synthetic else "live game",
        "counts": {t: len(rows.get(t, [])) for t in TABLES} | {"engine_calls": len(calls)},
        "metrics": out,
    }


# ---------------------------------------------------------------- live sources
def _sql(stdb: str, module: str, token: str, query: str) -> list[dict[str, Any]]:
    req = urllib.request.Request(
        f"{stdb}/v1/database/{module}/sql",
        data=query.encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        res = json.loads(r.read())[0]
    names = [c["name"].get("some") if isinstance(c["name"], dict) else c["name"] for c in res["schema"]["elements"]]
    return [dict(zip(names, row, strict=True)) for row in res["rows"]]


def fetch_rows(stdb: str, module: str, game: str) -> dict[str, list[dict[str, Any]]]:
    """The game's rows from Spacetime as contract objects. Public tables, read with an anonymous identity."""
    with urllib.request.urlopen(urllib.request.Request(f"{stdb}/v1/identity", method="POST"), timeout=10) as r:
        token = json.loads(r.read())["token"]
    if game == "latest":
        games = [json.loads(g["json"]) for g in _sql(stdb, module, token, "SELECT * FROM game")]
        if not games:
            raise SystemExit("no games in Spacetime")
        game = max(games, key=lambda g: float(g.get("t0_ms") or 0))["game_id"]
    if not re.fullmatch(r"g_[0-9a-z]{8}", game):
        raise SystemExit(f"bad game id {game!r}")
    q = "SELECT * FROM {} WHERE game_id = '{}'"
    return {t: [json.loads(r["json"]) for r in _sql(stdb, module, token, q.format(t, game))] for t in TABLES}


def read_local(data_dir: Path, game: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    acks = []
    p = data_dir / "logs" / "call_ack.jsonl"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            try:
                a = json.loads(line)
            except ValueError:
                continue
            if a.get("game_id") == game:
                acks.append(a)
    clips = [json.loads(m.read_text("utf8")) for m in sorted((data_dir / "clips" / game).glob("*/*.json"))]
    return acks, clips


def render(rep: dict[str, Any]) -> str:
    lines = [f"C3 timings for {rep['game_id']} ({rep['label']})", ""]
    lines.append(f"{'metric':<66} {'n':>4} {'p50 ms':>9} {'p95 ms':>9} {'max ms':>9} {'target':>8}  verdict")
    for m in rep["metrics"]:
        if m["n"]:
            nums = f"{m['p50_ms']:>9.1f} {m['p95_ms']:>9.1f} {m['max_ms']:>9.1f}"
        else:
            nums = f"{'—':>9} {'—':>9} {'—':>9}"
        tgt = f"{m['target_ms']:>8.0f}" if m["target_ms"] is not None else f"{'—':>8}"
        lines.append(f"{m['name'][:66]:<66} {m['n']:>4} {nums} {tgt}  {m['verdict']}")
    lines += ["", "Notes:"] + [f"- {m['name']}: {m['note']}" for m in rep["metrics"] if m["note"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--game", default="latest", help="game id, or `latest` (the newest t0; seeded synthetic games share one t0)"
    )
    ap.add_argument("--stdb", default="http://127.0.0.1:3000")
    ap.add_argument("--module", default="trophy")
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data" / "local")
    ap.add_argument("--log", type=Path, action="append", default=[], help="make dev output (repeatable)")
    ap.add_argument("--snapshot", type=Path, help="read {rows, acks, clips} from this JSON instead of the stack")
    ap.add_argument("--out", type=Path, help="report path (default data/local/c3/<game>.json)")
    a = ap.parse_args(argv)
    if a.snapshot:
        snap = json.loads(a.snapshot.read_text("utf8"))
        rows, acks, clips = snap["rows"], snap.get("acks", []), snap.get("clips", [])
    else:
        rows = fetch_rows(a.stdb, a.module, a.game)
        gid = (rows.get("game") or [{}])[0].get("game_id", a.game)
        acks, clips = read_local(a.data_dir, gid)
    logs = [ln for p in a.log for ln in p.read_text("utf8", errors="replace").splitlines()]
    rep = compute(rows, acks, clips, logs)
    rep["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    print(render(rep))
    out = a.out or (a.data_dir / "c3" / f"{rep['game_id']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + "\n", "utf8")
    if not a.snapshot:  # keep the inputs, so the numbers can be recomputed later
        snap_path = out.with_suffix(".rows.json")
        snap_path.write_text(json.dumps({"rows": rows, "acks": acks, "clips": clips}) + "\n", "utf8")
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

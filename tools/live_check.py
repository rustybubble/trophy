"""Live check through the running stack, as a phone + judge would: gateway -> frames -> flight -> engine -> Spacetime.

    uv run --project services/gateway --frozen python tools/live_check.py CLIP --taps x,y,x,y,x,y,x,y
                                       [--start 0 --seconds 10] [--first-server A] [--report out.json]

1. Creates a game (POST /api/games) and joins as cam+judge; syncs the clock over /api/ws/ctl.
2. Calibrates from four taps in the PWA's order (A_left, A_right, B_right, B_left), 1280x720 reference pixels, through
   POST /api/calibrate (the courtcam adapter, else the gateway's UNTRUSTED stub) and saves it (calib:{cam}, ctl:calib).
3. Starts the game (start_game on ctl:engine) and streams the clip at 30 fps in real time over /api/ws/frames, encoded
   like the PWA (libjpeg q70 4:2:0, `clip_as_phone.jpeg_frames`).
4. Waits, then reads back what the live services wrote for this game: flight's observations and track samples, and
   the engine's calls, rallies and score. Prints counts and per-type event times; nothing is hand-posted.

Whatever the clip is, this is a pipeline check, not an accuracy measurement (that needs labels: tools/eval_live.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import httpx
import websockets
from trophy.framebus import pack_header

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "gateway" / "scripts"))
from clip_as_phone import jpeg_frames  # noqa: E402

TAP_NAMES = ("A_left", "A_right", "B_right", "B_left")


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split(" #")[0].strip()
    return out


E = env()
BASE = f"http://127.0.0.1:{8000 + int(E.get('PORT_OFFSET') or 0)}"
STDB = (E.get("SPACETIME_URI") or "http://127.0.0.1:3000").rstrip("/")
MODULE = E.get("SPACETIME_MODULE") or "trophy"


def now_ms() -> float:
    return time.time() * 1000


def sql(query: str) -> list[dict]:
    req = urllib.request.Request(
        f"{STDB}/v1/database/{MODULE}/sql",
        data=query.encode(),
        method="POST",
        headers={"Content-Type": "text/plain", "Authorization": f"Bearer {E['SPACETIME_ENGINE_TOKEN']}"},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if not body:
        return []
    names = []
    for i, col in enumerate(body[0].get("schema", {}).get("elements", [])):
        n = col.get("name")
        n = n.get("some") if isinstance(n, dict) else n
        names.append(str(n) if n else f"col{i}")
    return [dict(zip(names, row, strict=False)) for row in body[0].get("rows", [])]


async def run(a) -> dict:
    taps = [float(v) for v in a.taps.split(",")]
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as http:
        g = (await http.post("/api/games", json={"sport": "table_tennis"})).json()
        j = (
            await http.post(
                f"/api/games/{g['game_id']}/join",
                json={"join_key": g["join_key"], "label": f"live-check:{a.clip.name}", "role": "cam,judge"},
            )
        ).json()
        tok, gid, cam = j["cam_token"], g["game_id"], j["cam_id"]
        auth = {"Authorization": f"Bearer {tok}"}
        req = {
            "schema": "trophy.calibration_request.v1",
            "game_id": gid,
            "cam_id": cam,
            "sport": "table_tennis",
            "seq": 0,
            "image_size": {"w": 1280, "h": 720},
            "points": [{"name": n, "px": [taps[2 * i], taps[2 * i + 1]]} for i, n in enumerate(TAP_NAMES)],
        }
        r = await http.post("/api/calibrate", json=req, headers=auth)
        r.raise_for_status()
        cal = r.json()
        r = await http.post(f"/api/cams/{cam}/calibration", json=cal, headers=auth)
        r.raise_for_status()
        print(
            json.dumps(
                {
                    "game_id": gid,
                    "cam_id": cam,
                    "calibration": cal.get("solver"),
                    "trusted": cal["trusted"],
                    "reproj_err_px": round(cal.get("reproj_err_px", 0), 2),
                }
            ),
            flush=True,
        )
        await asyncio.sleep(1.0)  # flight attaches to the new game (follow mode polls every 2 s)
        r = await http.post(
            "/api/ctl", json={"cmd": "start_game", "args": {"first_server": a.first_server}}, headers=auth
        )
        r.raise_for_status()

    ws_base = BASE.replace("http", "ws")
    async with websockets.connect(f"{ws_base}/api/ws/ctl?token={tok}") as ctl:
        prev = None
        for _ in range(10):
            t0 = now_ms()
            await ctl.send(json.dumps({"type": "ping", "t0": t0, **({"prev": prev} if prev else {})}))
            pong = json.loads(await ctl.recv())
            if prev:
                await ctl.recv()
            prev = {"t0": t0, "t1": pong["t1"], "t2": pong["t2"], "t3": now_ms()}
        await asyncio.sleep(a.lead_s)
        wall0 = now_ms() + 300
        sent = 0
        async with websockets.connect(f"{ws_base}/api/ws/frames?token={tok}", max_size=None) as fws:
            async for c, jpeg in jpeg_frames(a.clip, a.start, a.seconds):
                t_phone = wall0 + (c - a.start) * 1000
                await asyncio.sleep(max(0, (t_phone - now_ms()) / 1000))
                await fws.send(pack_header(sent, t_phone, 0) + jpeg)
                sent += 1
            stream_s = (now_ms() - wall0) / 1000
            clip_t0_game_s = (wall0 - g["t0_ms"]) / 1000
            await asyncio.sleep(a.tail_s)  # keep the socket: closing it would look like a camera dropping out
    q = f"WHERE game_id = '{gid}'"
    obs = sql(f"SELECT * FROM observation {q}")
    calls = sql(f"SELECT * FROM call {q}")
    rallies = sql(f"SELECT * FROM rally {q}")
    score = sql(f"SELECT * FROM score {q}")
    samples = sql(f"SELECT * FROM track_sample {q}")
    types = Counter(o.get("type") for o in obs)
    out = {
        "game_id": gid,
        "cam_id": cam,
        "frames_sent": sent,
        "stream_fps": round(sent / stream_s, 1) if stream_s else None,
        "clip_t0_game_s": round(clip_t0_game_s, 3),
        "observations": dict(types),
        "events": sorted(
            (round(float(o["t_game_s"]) - clip_t0_game_s + a.start, 3), o["type"], o.get("side"))
            for o in obs
            if o.get("type") != "heartbeat"
        ),
        "track_samples": len(samples),
        "calls": [
            {k: json.loads(c["json"]).get(k) for k in ("rule_id", "outcome", "tier", "p", "text", "t_game_s")}
            for c in calls
        ],
        "rallies": len(rallies),
        "score": {s.get("team_id"): s.get("points") for s in score},
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("clip", type=Path)
    ap.add_argument("--taps", required=True, help="A_left,A_right,B_right,B_left as x,y pairs (1280x720 px)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--first-server", default="A")
    ap.add_argument("--lead-s", type=float, default=2.0)
    ap.add_argument("--tail-s", type=float, default=3.0)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    out = asyncio.run(run(a))
    text = json.dumps(out, indent=1, default=str)
    print(text)
    if a.report:
        a.report.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

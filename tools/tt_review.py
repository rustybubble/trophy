"""Build a local review page for a tracked clip: video + ball overlay + side-elevation ball trail (metres) + rallies.

    uv run --project services/flight python tools/tt_review.py data/local/ttClips/side_IMG_4342.mp4 \
        data/local/tt-track/side_full.jsonl --out data/local/tt-review/side

Writes <out>/index.html, <out>/preview.mp4 (1280x720 H.264) and <out>/data.json under data/local (footage stays
local; nothing is published). Open index.html in a browser.

The side elevation is what one side-on camera can measure: distance along the table and height, scaled by the
table's known 2.74 m length in the image. Depth across the table is not observable from one camera, so it isn't
drawn. Positions are approximate (perspective, handheld camera) and labelled so.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
from pathlib import Path

from flight.rally import build_rallies
from flight.table import Table

TABLE_LEN_M = 2.74


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("track", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--serve", type=int, default=0, help="also serve the page on 127.0.0.1:<port> (with HTTP Range)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    raw = [json.loads(line) for line in a.track.read_text("utf8").splitlines()]
    tables = {r["seq"]: Table(*r["tb"][:4], r["tb"][4], r["tb"][5]) for r in raw if "tb" in r}

    def table_at(seq: int) -> Table | None:
        t = tables.get(seq)
        if t is None:
            return None
        half = max(t.net_x - t.x_left, t.x_right - t.net_x)
        return dataclasses.replace(t, x_left=t.net_x - half, x_right=t.net_x + half)

    rows = [dict(r, x=r.get("wx"), y=r.get("wy")) for r in raw]
    rallies = build_rallies(rows, table_at)

    track = []
    for r in rows:
        if r["state"] != "observed":
            continue
        tb = table_at(r["seq"])
        item = {"t": r["t"], "x": r["x"], "y": r["y"], "id": r["track_id"]}
        if tb is not None:
            ppm = (tb.x_right - tb.x_left) / TABLE_LEN_M  # pixels per metre along the table
            item["xm"] = round((r["x"] - tb.net_x) / ppm, 3)  # + toward end B
            item["zm"] = round((tb.top_y(r["x"]) + tb.thickness / 2 - r["y"]) / ppm, 3)  # height above the surface
        track.append(item)
    data = {
        "clip": a.clip.name,
        "track": track,
        "rallies": [dataclasses.asdict(r) for r in rallies],
        "table_len_m": TABLE_LEN_M,
    }
    (a.out / "data.json").write_text(json.dumps(data), encoding="utf8")
    prev = a.out / "preview.mp4"
    if not prev.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(a.clip),
                "-vf",
                "scale=1280:720",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-an",
                "-movflags",
                "+faststart",
                str(prev),
            ],
            check=True,
        )
    (a.out / "index.html").write_text(PAGE.replace("__DATA__", json.dumps(data)), encoding="utf8")
    decided = sum(r.winner is not None for r in rallies)
    print(f"{a.out / 'index.html'}: {len(rallies)} rallies ({decided} decided), {len(track)} ball points")
    if a.serve:
        serve(a.out, a.serve)


def serve(root: Path, port: int) -> None:
    """Static server with HTTP Range (video seeking needs it; http.server doesn't do ranges)."""
    import http.server
    import re

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kw):
            super().__init__(*args, directory=str(root), **kw)

        def send_head(self):
            rng = self.headers.get("Range")
            path = Path(self.translate_path(self.path))
            m = re.match(r"bytes=(\d+)-(\d*)", rng or "")
            if not m or not path.is_file():
                return super().send_head()
            size = path.stat().st_size
            start = int(m.group(1))
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
            f = path.open("rb")
            f.seek(start)
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(str(path)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.range_left = end - start + 1
            return f

        def copyfile(self, source, outputfile):
            left = getattr(self, "range_left", None)
            if left is None:
                return super().copyfile(source, outputfile)
            while left > 0:
                chunk = source.read(min(65536, left))
                if not chunk:
                    break
                outputfile.write(chunk)
                left -= len(chunk)

    print(f"serving http://127.0.0.1:{port}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trophy rally review</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#2a2f3a;--fg:#f3f4f6;--muted:#9ca3af;--a:#e4572e;--b:#2e86ab;--ball:#f59e0b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px -apple-system,system-ui,sans-serif}
header{padding:10px 16px;border-bottom:1px solid var(--line)}h1{font-size:18px;margin:0}.muted{color:var(--muted)}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:12px;padding:12px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.stage{position:relative}video,canvas.ov{width:100%;display:block}canvas.ov{position:absolute;inset:0;pointer-events:none}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px}
.rally{padding:8px;border-radius:8px;cursor:pointer;border:1px solid transparent}.rally:hover{border-color:var(--line)}
.rally.on{border-color:var(--ball)}.w{font-weight:700}.wa{color:var(--a)}.wb{color:var(--b)}
.ev{font:12px ui-monospace,monospace;color:var(--muted)}#side{width:100%;height:220px;display:block}
.row{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}button{background:#20242d;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 10px;cursor:pointer}
</style></head><body>
<header><h1>Rally review: <span id="clip"></span></h1>
<div class="muted">Ball positions come from the tracker (red = observed). Bounces (●) and hits (▲) and each point decision are
automatic; check them against the video. Side elevation: distance along the table and height above it, in approximate
metres (one side camera, handheld; depth across the table is not measurable from one camera).</div></header>
<main>
<div>
  <div class="stage"><video id="v" src="preview.mp4" controls muted playsinline></video><canvas class="ov" id="ov"></canvas></div>
  <div class="row"><button data-r="1">1×</button><button data-r="0.5">½×</button><button data-r="0.25">¼×</button>
  <button id="back">◀ frame</button><button id="fwd">frame ▶</button></div>
  <div class="panel" style="margin-top:10px"><div class="muted">Side elevation (m): A ← net → B</div><canvas id="side"></canvas></div>
</div>
<div class="panel"><div id="sum" class="muted"></div><div id="list"></div></div>
</main>
<script>
const D = __DATA__;
const v = document.getElementById("v"), ov = document.getElementById("ov"), side = document.getElementById("side");
document.getElementById("clip").textContent = D.clip;
const T = D.track, R = D.rallies;
const decided = R.filter(r => r.winner).length;
document.getElementById("sum").textContent = `${R.length} rallies, ${decided} with an automatic winner`;
const list = document.getElementById("list");
R.forEach((r, i) => {
  const d = document.createElement("div"); d.className = "rally"; d.dataset.i = i;
  const evs = r.events.map(e => `${e.kind === "bounce" ? "●" : e.kind === "hit" ? "▲" : "✕"}${e.side}@${e.t.toFixed(2)}`).join(" ");
  d.innerHTML = `<div><span class="w ${r.winner === "A" ? "wa" : r.winner === "B" ? "wb" : ""}">${r.winner ? "Point " + r.winner : "No decision"}</span>
    <span class="muted"> · ${r.t_start.toFixed(1)}–${r.t_end.toFixed(1)} s · conf ${r.confidence.toFixed(2)}</span></div>
    <div class="muted">${r.reason}</div><div class="ev">${evs}</div>`;
  d.onclick = () => { v.currentTime = Math.max(0, r.t_start - 0.5); v.play(); };
  list.appendChild(d);
});
document.querySelectorAll("[data-r]").forEach(b => b.onclick = () => v.playbackRate = +b.dataset.r);
document.getElementById("back").onclick = () => { v.pause(); v.currentTime -= 1 / 60; };
document.getElementById("fwd").onclick = () => { v.pause(); v.currentTime += 1 / 60; };

function lower(t) { let lo = 0, hi = T.length; while (lo < hi) { const m = (lo + hi) >> 1; if (T[m].t < t) lo = m + 1; else hi = m; } return lo; }
function draw() {
  const t = v.currentTime;
  const W = ov.width = v.clientWidth, H = ov.height = v.clientHeight, s = W / 1280;
  const g = ov.getContext("2d");
  const i = lower(t);
  // trail: the last 0.6 s of the CURRENT track only (never connect two tracks)
  const cur = T[i - 1];
  g.lineWidth = 2;
  if (cur && t - cur.t < 0.1) {
    g.strokeStyle = "rgba(239,68,68,.8)"; g.beginPath(); let started = false;
    for (let k = i - 1; k >= 0 && T[k].id === cur.id && t - T[k].t < 0.6; k--) {
      const p = T[k]; if (!started) { g.moveTo(p.x * s, p.y * s); started = true; } else g.lineTo(p.x * s, p.y * s);
    }
    g.stroke(); g.fillStyle = "#ef4444"; g.beginPath(); g.arc(cur.x * s, cur.y * s, 6, 0, 7); g.fill();
  }
  const r = R.find(r => t >= r.t_start - 0.2 && t <= r.t_end + 1.5);
  document.querySelectorAll(".rally").forEach(d => d.classList.toggle("on", r && +d.dataset.i === R.indexOf(r)));
  if (r) for (const e of r.events) {
    if (e.kind === "dead" || t < e.t || t - e.t > 1.0) continue;
    g.fillStyle = g.strokeStyle = e.side === "A" ? "#e4572e" : "#2e86ab";
    g.beginPath(); if (e.kind === "bounce") g.arc(e.x * s, e.y * s, 9, 0, 7); else { g.moveTo(e.x * s, e.y * s - 10); g.lineTo(e.x * s - 9, e.y * s + 7); g.lineTo(e.x * s + 9, e.y * s + 7); g.closePath(); }
    g.lineWidth = 3; g.stroke();
  }
  drawSide(t, r);
  requestAnimationFrame(draw);
}
function drawSide(t, r) {
  const W = side.width = side.clientWidth, H = side.height = side.clientHeight, g = side.getContext("2d");
  const half = D.table_len_m / 2, xm = x => W / 2 + x * (W / (D.table_len_m * 1.8)), zm = z => H - 30 - z * (H - 50) / 1.2;
  g.fillStyle = "#2b3a55"; g.fillRect(xm(-half), zm(0), xm(half) - xm(-half), 6);
  g.fillStyle = "#cbd5e1"; g.fillRect(xm(0) - 1, zm(0.1525), 2, zm(0) - zm(0.1525));
  g.fillStyle = "#9ca3af"; g.font = "12px system-ui"; g.fillText("A", xm(-half) - 14, zm(0) + 4); g.fillText("B", xm(half) + 6, zm(0) + 4);
  g.fillText("0.5 m", 4, zm(0.5)); g.fillRect(36, zm(0.5), 6, 1);
  const i = lower(t), cur = T[i - 1];
  if (!cur || t - cur.t > 0.15) return;
  g.strokeStyle = "rgba(245,158,11,.9)"; g.lineWidth = 2; g.beginPath(); let st = false;
  for (let k = i - 1; k >= 0 && T[k].id === cur.id && t - T[k].t < 1.2; k--) {
    const p = T[k]; if (p.xm === undefined) continue;
    if (!st) { g.moveTo(xm(p.xm), zm(p.zm)); st = true; } else g.lineTo(xm(p.xm), zm(p.zm));
  }
  g.stroke();
  if (cur.xm !== undefined) { g.fillStyle = "#f59e0b"; g.beginPath(); g.arc(xm(cur.xm), zm(cur.zm), 5, 0, 7); g.fill(); }
}
requestAnimationFrame(draw);
</script></body></html>
"""

if __name__ == "__main__":
    main()

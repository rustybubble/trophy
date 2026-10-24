"""P0 iPhone voice spike server: serves index.html, mints short-lived Cartesia tokens (the key never leaves
this process), and appends the phone's measured results to data/local/spikes/cartesia-iphone.jsonl.

    python spikes/cartesia-voice/serve.py [--port 8765]

The phone needs HTTPS (mic + audio): put this behind Caddy on the domain, or a tunnel for day 1.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VERSION = "2026-08-14"
TOKEN_TTL_S = 120


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


ENV = env()


def mint() -> dict:
    req = urllib.request.Request(
        "https://api.cartesia.ai/access-token",
        data=json.dumps({"grants": {"tts": True, "stt": True}, "expires_in": TOKEN_TTL_S}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {ENV['CARTESIA_API_KEY']}",
            "Cartesia-Version": ENV.get("CARTESIA_VERSION") or VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        token = json.loads(r.read())["token"]
    return {
        "access_token": token,
        "expires_at_ms": time.time() * 1000 + TOKEN_TTL_S * 1000,
        "cartesia_version": ENV.get("CARTESIA_VERSION") or VERSION,
        "voice": ENV.get("CARTESIA_VOICE_CALLS") or "a0e99841-438c-4a64-b679-ae501e7d6091",
    }


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/cam", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path.endswith("/voice/token"):
            try:
                self._send(200, json.dumps(mint()).encode(), "application/json")
            except Exception as e:  # don't leak details (or the key) to the client
                self.log_message("token mint failed: %s", type(e).__name__)
                self._send(502, b'{"error":"token mint failed"}', "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if self.path.split("?")[0].endswith("/spike/result"):
            body = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 65536))
            row = {"t_srv_ms": time.time() * 1000, **json.loads(body)}
            out = ROOT / "data" / "local" / "spikes"
            out.mkdir(parents=True, exist_ok=True)
            with (out / "cartesia-iphone.jsonl").open("a", encoding="utf8") as f:
                f.write(json.dumps(row) + "\n")
            self._send(204, b"", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    print(f"voice spike on http://{a.host}:{a.port}/  (needs HTTPS in front for the phone)")
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()

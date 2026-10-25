"""Reach the stack from phones on any network: a Cloudflare quick tunnel in front of Caddy (`make tunnel`).

Venue Wi-Fi often isolates devices, so phones can't reach the Mac's LAN IP even with trophy.photo pointing at it.
This opens an outbound tunnel (no account, no DNS change) and serves the stack at a random
https://<words>.trycloudflare.com address while it runs:

- requests go to Caddy (https://127.0.0.1:443) with Host and SNI = TROPHY_DOMAIN, so every route works as usual;
- the address is written to data/local/public_origin, which the gateway reads per request, so new join links and QR
  codes use it (and it is removed again when the tunnel stops).

Anyone with the address can open the app while it runs; game data and video still need a game's join link.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN_FILE = ROOT / "data" / "local" / "public_origin"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def domain() -> str:
    env = ROOT / ".env"
    for line in env.read_text("utf8").splitlines() if env.exists() else []:
        if line.startswith("TROPHY_DOMAIN="):
            return line.split("=", 1)[1].strip() or "trophy.photo"
    return os.environ.get("TROPHY_DOMAIN") or "trophy.photo"


def main() -> int:
    exe = shutil.which("cloudflared") or "/opt/homebrew/bin/cloudflared"
    host = domain()
    cmd = [
        exe, "tunnel", "--no-autoupdate", "--url", "https://127.0.0.1:443",
        "--http-host-header", host, "--origin-server-name", host,
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def stop(*_: object) -> None:
        ORIGIN_FILE.unlink(missing_ok=True)
        proc.terminate()

    # closing the terminal (SIGHUP) must clean up too, or the next run's links point at this dead address
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    ORIGIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    # a file left by a run that was killed names a dead tunnel: never keep it (it used to block the new address)
    ORIGIN_FILE.unlink(missing_ok=True)
    published = ""
    try:
        assert proc.stdout
        for line in proc.stdout:
            sys.stdout.write(line)
            m = URL_RE.search(line)
            if m and m.group(0) != published:
                published = m.group(0)
                ORIGIN_FILE.write_text(published + "\n", "utf8")
                print(f"\ntunnel: phones join at {m.group(0)}/cam/  (dashboard: {m.group(0)}/)\n", flush=True)
    finally:
        ORIGIN_FILE.unlink(missing_ok=True)
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())

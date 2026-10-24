"""Run Caddy for the dev origin with only the variables it needs from .env (TROPHY_DOMAIN, PORKBUN_*).

    python infra/caddy/run.py            # caddy run --config infra/caddy/Caddyfile.dev

Finds caddy on $CADDY, then PATH, then ~/.trophy/bin. Caddy must include caddy-dns/porkbun (infra/README.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEEDED = ("TROPHY_DOMAIN", "PORKBUN_API_KEY", "PORKBUN_SECRET_API_KEY")


def main() -> int:
    env = dict(os.environ)
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() in NEEDED:
                env[k.strip()] = v.split("#")[0].strip()
    missing = [k for k in NEEDED if not env.get(k)]
    if missing:
        print(f"missing in .env: {', '.join(missing)}", file=sys.stderr)
        return 1
    exe = env.get("CADDY") or shutil.which("caddy")
    if not exe:
        home = Path.home() / ".trophy" / "bin"
        exe = str(next((p for p in (home / "caddy.exe", home / "caddy") if p.exists()), "caddy"))
    cmd = [exe, "run", "--config", str(ROOT / "infra" / "caddy" / "Caddyfile.dev"), "--adapter", "caddyfile"]
    return subprocess.call(cmd, env=env, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())

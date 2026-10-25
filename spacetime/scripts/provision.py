"""Give each backend writer its own Spacetime identity (D-25) and register it with the module owner.

    python spacetime/scripts/provision.py            # after `spacetime publish ... trophy`

For each role (engine, vision, compiler): reuse SPACETIME_<ROLE>_TOKEN from .env or mint one with
POST /v1/identity, then call the owner-only reducer register_service with the owner's CLI token
(spacetimedb_token in cli.toml). Writes new tokens into .env and never prints them. Idempotent: rerun it
after re-publishing with --delete-data (the registrations live in the database).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
ROLES = ("engine", "vision", "compiler")


def read_env() -> dict[str, str]:
    out = {}
    for line in ENV_PATH.read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


def set_env(key: str, value: str) -> None:
    s = ENV_PATH.read_text("utf8")
    if re.search(rf"^{key}=.*$", s, flags=re.M):
        s = re.sub(rf"^{key}=.*$", f"{key}={value}", s, flags=re.M)
    else:
        s += f"\n{key}={value}\n"
    ENV_PATH.write_text(s, encoding="utf8", newline="\n")


def owner_token() -> str:
    candidates = [
        Path(os.environ["SPACETIME_ROOT"]) / "config" / "cli.toml" if os.environ.get("SPACETIME_ROOT") else None,
        Path.home() / ".spacetimedb" / "config" / "cli.toml",
        Path.home() / ".config" / "spacetime" / "cli.toml",
        Path.home() / ".local" / "share" / "spacetime" / "config" / "cli.toml",
        Path(os.environ.get("LOCALAPPDATA", "")) / "SpacetimeDB" / "config" / "cli.toml",
    ]
    for p in candidates:
        if p and p.exists():
            m = re.search(r'^spacetimedb_token\s*=\s*"([^"]+)"', p.read_text("utf8"), flags=re.M)
            if m:
                return m.group(1)
    raise SystemExit("owner token not found: publish the module first (it writes spacetimedb_token to cli.toml)")


def identity_of(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["hex_identity"].lower()


def post(url: str, body: object | None = None, token: str | None = None) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else b"", method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{url}: HTTP {e.code}: {e.read().decode()[:200]}") from None


def main() -> int:
    global ENV_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ENV_PATH)
    parser.add_argument(
        "--check-platform", action="store_true", help="exercise the platform reducers with real role tokens"
    )
    args = parser.parse_args()
    ENV_PATH = args.env_file
    env = read_env()
    env = {**env, **{k: os.environ[k] for k in ("SPACETIME_URI", "SPACETIME_MODULE") if os.environ.get(k)}}  # compose
    uri = (env.get("SPACETIME_URI") or "http://127.0.0.1:3000").rstrip("/")
    module = env.get("SPACETIME_MODULE") or "trophy"
    owner = owner_token()
    for role in ROLES:
        key = f"SPACETIME_{role.upper()}_TOKEN"
        token = env.get(key, "")
        if not token:
            token = json.loads(post(f"{uri}/v1/identity"))["token"]
            set_env(key, token)
            minted = "minted"
        else:
            minted = "reused"
        ident = identity_of(token)
        payload = json.dumps({"identity_hex": ident, "role": role, "label": f"trophy-{role}"})
        post(f"{uri}/v1/database/{module}/call/register_service", [payload], owner)
        print(f"{role}: {minted} identity {ident[:16]}…, registered in {module}")
    if args.check_platform:
        from check_platform import check_platform

        check_platform(read_env())
    return 0


if __name__ == "__main__":
    sys.exit(main())

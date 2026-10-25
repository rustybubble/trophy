"""Settings from the environment, with the repo's .env as a fallback (never logged)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _dotenv() -> dict[str, str]:
    p = ROOT / ".env"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


@dataclass(frozen=True)
class Settings:
    token_secret: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    domain: str = "trophy.photo"
    port: int = 8000
    stdb_public_uri: str = "wss://trophy.photo/stdb"
    stdb_module: str = "trophy"
    stdb_http: str = "http://127.0.0.1:3000"
    adapter_url: str = "http://127.0.0.1:8050"
    rules_url: str = "http://127.0.0.1:8100"
    cartesia_api_key: str = ""
    cartesia_version: str = "2026-08-14"
    cartesia_voice_calls: str = ""
    cartesia_voice_ref: str = ""
    voice_token_ttl_s: int = 600
    cam_token_ttl_s: int = 12 * 3600
    data_dir: Path = ROOT / "data" / "local"

    @classmethod
    def from_env(cls) -> Settings:
        env = {**_dotenv(), **os.environ}
        secret = env.get("TROPHY_TOKEN_SECRET", "")
        if len(secret) < 16:
            raise SystemExit("TROPHY_TOKEN_SECRET must be set (>= 16 chars) in .env")
        off = int(env.get("PORT_OFFSET") or 0)
        domain = env.get("TROPHY_DOMAIN") or "trophy.photo"
        return cls(
            token_secret=secret,
            redis_url=env.get("REDIS_URL") or cls.redis_url,
            domain=domain,
            port=8000 + off,
            stdb_public_uri=env.get("SPACETIME_PUBLIC_URI") or f"wss://{domain}/stdb",
            stdb_module=env.get("SPACETIME_MODULE") or "trophy",
            stdb_http=(env.get("SPACETIME_URI") or cls.stdb_http).rstrip("/"),
            adapter_url=env.get("ADAPTER_URL") or f"http://127.0.0.1:{8050 + off}",
            rules_url=env.get("RULES_URL") or f"http://127.0.0.1:{8100 + off}",
            cartesia_api_key=env.get("CARTESIA_API_KEY", ""),
            cartesia_version=env.get("CARTESIA_VERSION") or cls.cartesia_version,
            cartesia_voice_calls=env.get("CARTESIA_VOICE_CALLS", ""),
            cartesia_voice_ref=env.get("CARTESIA_VOICE_REF", ""),
            data_dir=Path(env["TROPHY_DATA_DIR"]) if env.get("TROPHY_DATA_DIR") else cls.data_dir,
        )

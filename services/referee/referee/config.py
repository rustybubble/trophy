"""Settings. Every external dependency needs its real key: there is no keyless, stub or canned-answer mode."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Cartesia library voices (listed with GET /voices on 2026-10-24): crisp male for calls, confident female for the ref.
DEFAULT_VOICES = {
    "calls": "47c38ca4-5f35-497b-b1a3-415245fb35e1",  # Daniel - Modern Assistant
    "ref": "62ae83ad-4f6a-430b-af41-a9bede9286ca",  # Gemma - Decisive Agent
}


class ConfigError(SystemExit):
    pass


def _dotenv(path: Path = ROOT / ".env") -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text("utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return out


@dataclass
class Settings:
    anthropic_api_key: str
    cartesia_api_key: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    port: int = 8100
    claude_model: str = "claude-opus-5-5"  # phrasing and rule answers
    claude_fast_model: str = "claude-haiku-5-5"  # the question router
    cartesia_version: str = "2026-08-14"
    tts_model: str = "sonic-3.6"
    voices: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VOICES))
    sample_rate: int = 24000
    speaker: bool = False  # play the ref voice on this machine's audio output (needs the `speaker` extra)
    sports_dir: Path = ROOT / "sports"
    data_dir: Path = ROOT / "data" / "local"
    check_timeout_s: float = 1.5  # a cached check answers in ms; this bounds a stalled engine
    pending_timeout_s: float = 95.0  # the Droid's 90 s cap plus the gate
    phrase_timeout_s: float = 6.0

    @classmethod
    def from_env(
        cls, env: dict[str, str] | None = None, *, require: tuple[str, ...] = ("ANTHROPIC_API_KEY", "CARTESIA_API_KEY")
    ) -> Settings:
        """`require` names the keys this entry point needs: the service needs both, `referee speak` only Cartesia."""
        e = {**_dotenv(), **os.environ, **(env or {})}
        anthropic = e.get("ANTHROPIC_API_KEY", "")
        cartesia = e.get("CARTESIA_API_KEY", "")
        missing = [k for k in require if not e.get(k)]
        if missing:
            raise ConfigError(f"referee: {', '.join(missing)} must be set in .env (no keyless mode)")
        off = int(e.get("PORT_OFFSET") or 0)
        voices = {
            "calls": e.get("CARTESIA_VOICE_CALLS") or DEFAULT_VOICES["calls"],
            "ref": e.get("CARTESIA_VOICE_REF") or DEFAULT_VOICES["ref"],
        }
        return cls(
            anthropic_api_key=anthropic,
            cartesia_api_key=cartesia,
            redis_url=e.get("REDIS_URL") or cls.redis_url,
            port=int(e.get("REFEREE_PORT") or 8100 + off),
            claude_model=e.get("CLAUDE_MODEL") or cls.claude_model,
            claude_fast_model=e.get("CLAUDE_FAST_MODEL") or cls.claude_fast_model,
            cartesia_version=e.get("CARTESIA_VERSION") or cls.cartesia_version,
            voices=voices,
            speaker=(e.get("REFEREE_SPEAKER") or "0") in ("1", "true", "yes"),
            sports_dir=Path(e["TROPHY_SPORTS_DIR"]) if e.get("TROPHY_SPORTS_DIR") else cls.sports_dir,
            data_dir=Path(e["TROPHY_DATA_DIR"]) if e.get("TROPHY_DATA_DIR") else cls.data_dir,
        )

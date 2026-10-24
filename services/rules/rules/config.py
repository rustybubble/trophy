"""Settings from the environment, with the repo's `.env` / `.env.local` as fallbacks (secrets never logged or repr'd).

The three credentials are required: `require_keys()` raises `ConfigError` naming the missing ones, and the CLI
turns that into exit code 3. There is no keyless mode, no mock index and no canned answer anywhere in this service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REQUIRED = ("ANTHROPIC_API_KEY", "MOSS_PROJECT_ID", "MOSS_PROJECT_KEY")


def _dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in (".env", ".env.local"):  # later files win; the process environment wins over both
        p = ROOT / name
        if not p.exists():
            continue
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return out


@dataclass(frozen=True)
class Settings:
    port: int = 8100
    anthropic_api_key: str = field(default="", repr=False)
    moss_project_id: str = field(default="", repr=False)
    moss_project_key: str = field(default="", repr=False)
    apify_token: str = field(default="", repr=False)
    ask_model: str = "claude-opus-5-5"
    ask_effort: str = "low"
    ask_min_score: float = 0.35  # below this top Moss score /ask says it couldn't find the rule (tune on the eval set)
    ask_top_k: int = 5
    moss_index: str = "trophy-rules-v1"
    moss_model: str = "moss-minilm"
    moss_cache_path: Path = ROOT / "data" / "local" / "moss"
    apify_actor: str = "trophy/sports-rulebook-scraper"
    rulebooks_dir: Path = ROOT / "data" / "local" / "rulebooks"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = {**_dotenv(), **os.environ, **(env or {})}
        off = int(env.get("PORT_OFFSET") or 0)
        return cls(
            port=8100 + off,
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            moss_project_id=env.get("MOSS_PROJECT_ID", ""),
            moss_project_key=env.get("MOSS_PROJECT_KEY", ""),
            apify_token=env.get("APIFY_TOKEN", ""),
            ask_model=env.get("ASK_MODEL") or cls.ask_model,
            ask_effort=env.get("ASK_EFFORT") or cls.ask_effort,
            ask_min_score=float(env.get("ASK_MIN_SCORE") or cls.ask_min_score),
            ask_top_k=int(env.get("ASK_TOP_K") or cls.ask_top_k),
            moss_index=env.get("MOSS_INDEX") or cls.moss_index,
            moss_model=env.get("MOSS_MODEL") or cls.moss_model,
            moss_cache_path=Path(env.get("MOSS_CACHE_PATH") or cls.moss_cache_path),
            apify_actor=env.get("APIFY_RULEBOOK_ACTOR") or cls.apify_actor,
        )

    def missing_keys(self) -> list[str]:
        present = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "MOSS_PROJECT_ID": self.moss_project_id,
            "MOSS_PROJECT_KEY": self.moss_project_key,
        }
        return [k for k in REQUIRED if not present[k]]

    def require_keys(self) -> None:
        from .errors import ConfigError

        missing = self.missing_keys()
        if missing:
            raise ConfigError(f"rules: refusing to start without {', '.join(missing)} (set them in .env)")

    def presence(self) -> dict[str, bool]:
        """Which credentials are set (booleans only; safe to log)."""
        return {
            "anthropic": bool(self.anthropic_api_key),
            "moss": bool(self.moss_project_id and self.moss_project_key),
            "apify": bool(self.apify_token),
        }

"""Settings from the environment, with the repo's .env as a fallback (secrets are never logged or repr'd)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    port: int = 8100
    anthropic_api_key: str = field(default="", repr=False)
    claude_model: str = "claude-opus-5-5"
    moss_project_id: str = field(default="", repr=False)
    moss_project_key: str = field(default="", repr=False)
    moss_model: str = "moss-minilm"
    moss_cache_path: Path = ROOT / "data" / "local" / "moss"
    apify_token: str = field(default="", repr=False)
    apify_actor: str = "trophy/sports-rulebook-scraper"
    top_k: int = 5
    min_score: float = 0.35  # below this the top hit is "weak retrieval": we say we couldn't find the rule

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = {**_dotenv(), **os.environ, **(env or {})}
        off = int(env.get("PORT_OFFSET") or 0)
        return cls(
            port=8100 + off,
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            claude_model=env.get("CLAUDE_MODEL") or cls.claude_model,
            moss_project_id=env.get("MOSS_PROJECT_ID", ""),
            moss_project_key=env.get("MOSS_PROJECT_KEY", ""),
            moss_model=env.get("MOSS_MODEL") or cls.moss_model,
            moss_cache_path=Path(env.get("MOSS_CACHE_PATH") or cls.moss_cache_path),
            apify_token=env.get("APIFY_TOKEN", ""),
            apify_actor=env.get("APIFY_RULEBOOK_ACTOR") or cls.apify_actor,
            top_k=int(env.get("RULES_TOP_K") or cls.top_k),
            min_score=float(env.get("RULES_MIN_SCORE") or cls.min_score),
        )

    def presence(self) -> dict[str, bool]:
        """Which credentials are set (booleans only; safe to log and to return from /healthz)."""
        return {
            "anthropic": bool(self.anthropic_api_key),
            "moss": bool(self.moss_project_id and self.moss_project_key),
            "apify": bool(self.apify_token),
        }

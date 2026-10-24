"""Real third-party clients, built lazily and only with their credentials.

Every constructor raises ConfigError when its key is missing. There is no keyless mode: the
service reports 503 instead of inventing an answer. Verified against the installed SDKs on
2026-10-24: moss 1.21 (`MossClient(project_id, project_key, cache_path=)`), anthropic 2.3
(`AsyncAnthropic(api_key=)`), apify-client 3.3 (`ApifyClient(token)`).
"""

from __future__ import annotations

from .config import Settings
from .errors import ConfigError


def moss_client(s: Settings):
    if not (s.moss_project_id and s.moss_project_key):
        raise ConfigError("Moss needs MOSS_PROJECT_ID and MOSS_PROJECT_KEY (from the Moss portal) in .env")
    from moss import MossClient

    s.moss_cache_path.mkdir(parents=True, exist_ok=True)
    return MossClient(s.moss_project_id, s.moss_project_key, cache_path=str(s.moss_cache_path))


def anthropic_client(s: Settings):
    if not s.anthropic_api_key:
        raise ConfigError("Claude needs ANTHROPIC_API_KEY in .env")
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=s.anthropic_api_key)


def apify_client(s: Settings):
    if not s.apify_token:
        raise ConfigError("Pulling the actor's dataset needs APIFY_TOKEN in .env")
    from apify_client import ApifyClient

    return ApifyClient(s.apify_token)

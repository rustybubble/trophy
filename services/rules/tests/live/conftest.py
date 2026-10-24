"""Live tests: they call Moss and Claude with the real keys and are skipped, with the reason printed, without them.

Run: `uv run pytest -q -rs tests/live -s` from services/rules with ANTHROPIC_API_KEY, MOSS_PROJECT_ID and
MOSS_PROJECT_KEY in the environment (or the repo's .env). They print the measured numbers (brief §3 P0 spikes a, b).
"""

from __future__ import annotations

import pytest

from rules.config import Settings


def pytest_collection_modifyitems(config, items):
    s = Settings.from_env()
    missing = s.missing_keys()
    if not missing:
        return
    reason = f"live test skipped: {', '.join(missing)} not set (no keyless mode; see tests/live/conftest.py)"
    for item in items:
        if "live" in item.keywords:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    return Settings.from_env()

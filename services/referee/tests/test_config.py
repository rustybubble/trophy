import pytest

from referee.config import ConfigError, Settings


def test_refuses_to_start_without_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.setattr("referee.config._dotenv", lambda *a, **k: {})
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_env_wins_and_defaults(monkeypatch):
    monkeypatch.setattr("referee.config._dotenv", lambda *a, **k: {})
    st = Settings.from_env({"ANTHROPIC_API_KEY": "a", "CARTESIA_API_KEY": "c", "CARTESIA_VOICE_REF": "v-ref"})
    assert st.voices["ref"] == "v-ref" and st.voices["calls"] == "47c38ca4-5f35-497b-b1a3-415245fb35e1"
    assert st.port == 8100
    only = Settings.from_env({"CARTESIA_API_KEY": "c"}, require=("CARTESIA_API_KEY",))
    assert only.anthropic_api_key == ""
    assert st.claude_model == "claude-opus-5-5" and st.claude_fast_model == "claude-haiku-5-5"

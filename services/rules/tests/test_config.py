"""No keys, no run: the CLI exits 3 with one line; no route answers without Moss and Claude; secrets never repr."""

import pytest

from rules import cli
from rules.clients import anthropic_client, apify_client, moss_client
from rules.config import Settings
from rules.errors import ConfigError


@pytest.fixture
def keyless(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "MOSS_PROJECT_ID", "MOSS_PROJECT_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(cli, "Settings", type("S", (), {"from_env": staticmethod(lambda: Settings())}))


def test_missing_keys_are_named():
    assert Settings().missing_keys() == ["ANTHROPIC_API_KEY", "MOSS_PROJECT_ID", "MOSS_PROJECT_KEY"]
    assert Settings(anthropic_api_key="a", moss_project_id="p").missing_keys() == ["MOSS_PROJECT_KEY"]
    with pytest.raises(ConfigError, match="MOSS_PROJECT_KEY"):
        Settings(anthropic_api_key="a", moss_project_id="p").require_keys()


def test_clients_require_their_keys():
    for fn, msg in (
        (moss_client, "MOSS_PROJECT_ID"),
        (anthropic_client, "ANTHROPIC_API_KEY"),
        (apify_client, "APIFY_TOKEN"),
    ):
        with pytest.raises(ConfigError, match=msg):
            fn(Settings())


def test_secrets_are_not_in_repr():
    s = Settings(
        anthropic_api_key="sk-ant-SECRET1",
        moss_project_id="proj-SECRET2",
        moss_project_key="SECRET3",
        apify_token="apify_SECRET4",
    )
    assert "SECRET" not in repr(s) and "SECRET" not in str(s)
    assert s.presence() == {"anthropic": True, "moss": True, "apify": True}


@pytest.mark.parametrize(
    "argv",
    [["serve"], ["index", "status"], ["index", "build"], ["eval", "--sport", "paddle_pong"], ["check-pack", "x.yaml"]],
)
def test_cli_exits_3_without_keys(keyless, capsys, argv):
    assert cli.main(argv) == 3
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("rules: refusing to start without ANTHROPIC_API_KEY")


def test_settings_from_env_knobs(monkeypatch):
    for k, v in {"ASK_MODEL": "claude-haiku-5-5", "ASK_EFFORT": "medium", "ASK_MIN_SCORE": "0.5", "ASK_TOP_K": "7",
                 "MOSS_INDEX": "trophy-rules-v2", "PORT_OFFSET": "200"}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    assert (s.ask_model, s.ask_effort, s.ask_min_score, s.ask_top_k, s.moss_index, s.port) == (
        "claude-haiku-5-5", "medium", 0.5, 7, "trophy-rules-v2", 8300)  # fmt: skip


async def test_startup_fails_fast_when_the_index_is_not_built(moss, settings):
    from rules.search import RuleStore

    store = RuleStore(moss, index="trophy-rules-v1")
    with pytest.raises(ConfigError, match="trophy-rules index build"):
        await store.load()

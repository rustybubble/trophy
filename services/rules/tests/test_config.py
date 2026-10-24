"""Without keys the app imports, /healthz serves, every network-backed route is 503, and the CLI refuses."""

import pytest
from fastapi.testclient import TestClient

from rules import app as app_mod
from rules import cli
from rules.clients import anthropic_client, apify_client, moss_client
from rules.config import Settings
from rules.errors import ConfigError


@pytest.fixture
def keyless(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "MOSS_PROJECT_ID", "MOSS_PROJECT_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(app_mod, "get_settings", lambda: Settings(), raising=True)
    app_mod.get_store.cache_clear()
    app_mod.get_llm.cache_clear()
    app_mod.app.dependency_overrides[app_mod.get_settings] = lambda: Settings()
    yield
    app_mod.app.dependency_overrides.clear()


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
    assert Settings(moss_project_id="only-id").presence()["moss"] is False


def test_routes_return_503_without_keys(keyless):
    client = TestClient(app_mod.app)
    assert client.get("/healthz").json()["keys"] == {"anthropic": False, "moss": False, "apify": False}
    r = client.post("/ask", json={"question": "q", "sport": "table_tennis"})
    assert r.status_code == 503 and "MOSS_PROJECT_ID" in r.json()["detail"]
    r = client.post("/coach", json={"game_id": "g", "sport": "s", "side": "Blue", "stats": {"points": 1}})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert client.get("/rule_ref", params={"sport": "x", "q": "y"}).status_code == 503
    assert client.post("/search_moments", json={"game_id": "g", "q": "x"}).status_code == 503


def test_cli_refuses_without_keys(keyless, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls, env=None: Settings()))
    p = tmp_path / "rules.jsonl"
    p.write_text(
        '{"sport":"table_tennis","rule_id":"2.6.2","title":"t","text":"The server shall project the ball.","url":"u"}\n'
    )
    assert cli.main(["index", "load-local", str(p)]) == 3
    assert "MOSS_PROJECT_ID" in capsys.readouterr().err
    assert cli.main(["index", "build", "--sport", "table_tennis"]) == 3
    assert "APIFY_TOKEN" in capsys.readouterr().err


def test_cli_builds_from_local_file_with_injected_moss(tmp_path, monkeypatch, capsys):
    from conftest import FakeMoss

    fake = FakeMoss()
    monkeypatch.setattr(cli, "moss_client", lambda s: fake)
    monkeypatch.setattr(
        cli.Settings, "from_env", classmethod(lambda cls, env=None: Settings(moss_project_id="p", moss_project_key="k"))
    )
    p = tmp_path / "rules.jsonl"
    p.write_text(
        '{"sport":"table_tennis","rule_id":"2.6.2","title":"t","text":"The server shall project the ball.","url":"u"}\n'
        '{"sport":"pickleball","rule_id":"7.A","title":"t","text":"Hitting the ball into your own side.","url":"u"}\n'
    )
    assert cli.main(["index", "load-local", str(p)]) == 0
    out = capsys.readouterr().out
    assert "rules-table_tennis: 1" in out and "rules-pickleball: 1" in out
    assert fake.indexes["rules-table_tennis"]["2.6.2"]["metadata"]["rule_id"] == "2.6.2"
    assert cli.main(["index", "build", "--local", str(p), "--sport", "pickleball"]) == 0

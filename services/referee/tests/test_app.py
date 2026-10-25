from conftest import CTX, FakeLLM
from fastapi.testclient import TestClient

from referee.app import create_app


class NoTTS:
    connected = False
    connect_ms = None
    sinks: list = []

    def add_sink(self, s):
        self.sinks.append(s)

    async def start(self):
        pass

    async def stop(self):
        pass

    async def speak(self, text, **kw):
        raise RuntimeError("offline")


def test_endpoints(settings, redis_client):
    llm = FakeLLM()
    app = create_app(settings, r=redis_client, llm=llm, tts=NoTTS(), start_tts=False)
    with TestClient(app) as c:
        h = c.get("/healthz").json()
        assert h["ok"] and h["redis"] is True and "in_out" in h["checks"] and h["claude_model"] == "claude-opus-5-5"
        assert c.get("/checks").json()["checks"][0]["name"] == "in_out"
        s = c.post("/ask", json={"game_id": "g1", "question": "what's the score", "context": CTX}).json()
        assert s["kind"] == "score" and s["speech"].startswith("7 to 5")
        assert c.post("/ask", json={"game_id": "g1", "question": ""}).status_code == 422
        assert c.post("/speak", json={"text": "hi", "voice": "nope"}).status_code == 422
        assert c.post("/speak", json={"text": "hi"}).status_code == 502
        assert c.get("/listen").status_code == 200 and "ws/audio" in c.get("/listen").text
        with c.websocket_connect("/ws/audio") as ws:
            assert ws.receive_json()["sample_rate"] == 24000

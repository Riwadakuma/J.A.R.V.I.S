from fastapi.testclient import TestClient
from controller.app import app
import controller.app as capp


def test_chat_branch(monkeypatch):
    monkeypatch.setattr(capp, "_resolver", None)
    monkeypatch.setattr(capp, "ollama_chat", lambda **kwargs: "hi")
    client = TestClient(app)
    r = client.post("/chat", json={"text": "привет"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "chat"
    assert data["text"] == "hi"


def test_command_with_proxy(monkeypatch):
    monkeypatch.setattr(capp, "_resolver", None)
    monkeypatch.setattr(capp, "_proxy_commands", True)

    class DummyResp:
        status_code = 200
        headers = {"content-type": "application/json"}
        def json(self):
            return {"ok": True, "result": "done", "error": None}

    class DummyClient:
        def __init__(self, timeout):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            pass
        def post(self, url, json, headers):
            assert json["command"] == "files.list"
            return DummyResp()

    monkeypatch.setattr(capp.httpx, "Client", DummyClient)
    client = TestClient(app)
    r = client.post("/chat", json={"text": 'файлы "*.txt"'})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "command"
    assert data["ok"] is True
    assert data["result"] == "done"


def test_toolrunner_error(monkeypatch):
    monkeypatch.setattr(capp, "_resolver", None)
    monkeypatch.setattr(capp, "_proxy_commands", True)

    class DummyClient:
        def __init__(self, timeout):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            pass
        def post(self, url, json, headers):
            raise RuntimeError("boom")

    monkeypatch.setattr(capp.httpx, "Client", DummyClient)
    client = TestClient(app)
    r = client.post("/chat", json={"text": 'файлы "*.txt"'})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "command"
    assert data["ok"] is False
    assert data["error"].startswith("E_TOOLRUNNER")

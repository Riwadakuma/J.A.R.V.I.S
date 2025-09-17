from fastapi.testclient import TestClient
from interaction.resolver.main import app


def test_resolve_simple(monkeypatch, tmp_path):
    client = TestClient(app)
    (tmp_path / "foo.txt").write_text("hi", encoding="utf-8")
    payload = {
        "trace_id": "1",
        "text": 'прочитай "foo.txt"',
        "context": {"cwd": str(tmp_path)},
        "constraints": {},
        "config": {},
    }
    r = client.post("/resolve", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["command"] == "files.read"
    assert data["args"]["path"] == "foo.txt"


def test_resolve_whitelist(tmp_path):
    client = TestClient(app)
    (tmp_path / "foo.txt").write_text("hi", encoding="utf-8")
    payload = {
        "trace_id": "1",
        "text": 'прочитай "foo.txt"',
        "context": {"cwd": str(tmp_path)},
        "constraints": {"whitelist": ["files.list"]},
        "config": {},
    }
    r = client.post("/resolve", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["command"] == "files.list"
    assert data["fallback_used"] is True
    assert "whitelist:forced_fallback" in data["explain"]


def test_resolve_create_with_content(monkeypatch, tmp_path):
    client = TestClient(app)
    payload = {
        "trace_id": "1",
        "text": 'создай файл "foo.txt" с содержимым привет',
        "context": {"cwd": str(tmp_path)},
        "constraints": {},
        "config": {},
    }
    monkeypatch.setattr("interaction.resolver.pipeline.ask_ollama", lambda *args, **kwargs: None)
    r = client.post("/resolve", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["command"] == "files.create"
    assert data["args"]["path"] == "foo.txt"
    assert data["args"]["content"] == "привет"


def test_resolve_append_with_content(monkeypatch, tmp_path):
    client = TestClient(app)
    (tmp_path / "foo.txt").write_text("start", encoding="utf-8")
    payload = {
        "trace_id": "1",
        "text": 'допиши в файл "foo.txt": привет',
        "context": {"cwd": str(tmp_path)},
        "constraints": {},
        "config": {},
    }
    monkeypatch.setattr("interaction.resolver.pipeline.ask_ollama", lambda *args, **kwargs: None)
    r = client.post("/resolve", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["command"] == "files.append"
    assert data["args"]["path"] == "foo.txt"
    assert data["args"]["content"] == "привет"

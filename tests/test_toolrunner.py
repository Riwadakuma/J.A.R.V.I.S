from fastapi.testclient import TestClient
from toolrunner.app import app
import toolrunner.app as tr_app


def test_file_commands_and_sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(tr_app, "_config", {"paths": {"workspace": str(tmp_path)}})
    client = TestClient(app)

    r = client.post("/execute", json={"command": "files.create", "args": {"path": "a.txt", "content": "hi"}})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.post("/execute", json={"command": "files.read", "args": {"path": "a.txt"}})
    assert r.status_code == 200
    assert r.json()["result"] == "hi"

    r = client.post("/execute", json={"command": "files.read", "args": {"path": "../b.txt"}})
    assert r.status_code == 400
    assert r.json()["detail"] == "E_PATH_OUTSIDE_WORKSPACE"

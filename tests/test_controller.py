from fastapi.testclient import TestClient
from controller.app import app
import controller.app as capp
import controller.resolver_adapter as cra
import toolrunner.app as tapp
import interaction.resolver.main as resolver_main


def test_chat_branch(monkeypatch):
    monkeypatch.setattr(capp, "_pipeline", None)
    monkeypatch.setattr(capp, "_planner_enabled", False)
    monkeypatch.setattr(capp, "_resolver", None)
    monkeypatch.setattr(capp, "ollama_chat", lambda **kwargs: "hi")
    client = TestClient(app)
    r = client.post("/chat", json={"text": "привет"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "chat"
    assert data["text"] == "hi"


def test_command_with_proxy(monkeypatch):
    monkeypatch.setattr(capp, "_pipeline", None)
    monkeypatch.setattr(capp, "_planner_enabled", False)
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
    monkeypatch.setattr(capp, "_pipeline", None)
    monkeypatch.setattr(capp, "_planner_enabled", False)
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


def test_controller_toolrunner_appends_content(monkeypatch, tmp_path):
    monkeypatch.setattr(capp, "_pipeline", None)
    monkeypatch.setattr(capp, "_planner_enabled", False)
    monkeypatch.setattr(capp, "_resolver", None)
    monkeypatch.setattr(capp, "_proxy_commands", True)
    monkeypatch.setattr(tapp, "_config", {"paths": {"workspace": str(tmp_path)}})

    tr_client = TestClient(tapp.app)
    captured: list[dict] = []

    class ToolrunnerClient:
        def __init__(self, timeout):
            self._timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def post(self, url, json, headers):
            captured.append(json)
            return tr_client.post("/execute", json=json)

    monkeypatch.setattr(capp.httpx, "Client", ToolrunnerClient)

    client = TestClient(app)
    r = client.post("/chat", json={"text": "допиши в файл note.txt: привет"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "command"
    assert data["command"] == "files.append"
    assert data["ok"] is True
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "привет"
    assert captured[-1]["args"]["content"] == "привет"
    assert "text" not in captured[-1]["args"]


def test_controller_resolver_toolrunner_create_content(monkeypatch, tmp_path):
    monkeypatch.setattr(capp, "_pipeline", None)
    monkeypatch.setattr(capp, "_planner_enabled", False)
    monkeypatch.setattr(tapp, "_config", {"paths": {"workspace": str(tmp_path)}})
    monkeypatch.setattr(capp, "_proxy_commands", True)
    monkeypatch.setattr(capp, "_workspace_root", str(tmp_path))
    monkeypatch.setattr(capp, "_ru_quick_intent", lambda text: None)

    tr_client = TestClient(tapp.app)
    resolver_client = TestClient(resolver_main.app)
    captured: list[dict] = []

    class MultiplexClient:
        def __init__(self, timeout):
            self._timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def post(self, url, json, headers=None):
            if url.endswith("/execute"):
                captured.append(json)
                return tr_client.post("/execute", json=json, headers=headers or {})
            if url.endswith("/resolve"):
                return resolver_client.post("/resolve", json=json)
            raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(capp.httpx, "Client", MultiplexClient)
    monkeypatch.setattr(cra.httpx, "Client", MultiplexClient)

    import interaction.resolver.pipeline as resolver_pipeline

    monkeypatch.setattr(resolver_pipeline, "ask_ollama", lambda *args, **kwargs: None)

    adapter = cra.ResolverAdapter(
        base_url="http://resolver",
        whitelist=list(capp._WHITELIST_RESOLVER),
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr(capp, "_resolver", adapter)

    client = TestClient(app)
    r = client.post("/chat", json={"text": "создай файл note.txt с содержимым привет"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "command"
    assert data["command"] == "files.create"
    assert data["ok"] is True
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "привет"
    assert captured[-1]["args"]["content"] == "привет"
    assert "text" not in captured[-1]["args"]


def test_pipeline_executes_with_local_transport(monkeypatch, tmp_path):
    from core.pipeline import build_local_pipeline
    from resolver.resolver import ResolverConfig

    resolver_cfg = ResolverConfig(
        whitelist=list(capp._WHITELIST_RESOLVER),
        remote_url=None,
        mode="quick",
    )
    pipeline = build_local_pipeline(
        resolver_config=resolver_cfg,
        planner_rules_path=capp._planner_rules_path,
        toolrunner_config={"paths": {"workspace": str(tmp_path)}},
        strict_acl=True,
    )
    monkeypatch.setattr(capp, "_pipeline", pipeline)
    monkeypatch.setattr(capp, "_planner_enabled", True)
    monkeypatch.setattr(capp, "_workspace_root", str(tmp_path))

    client = TestClient(app)
    r = client.post("/chat", json={"text": "создай файл alpha.txt с содержимым тест"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "command"
    assert data["ok"] is True
    assert data["command"] == "files.create"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "тест"
    meta = data.get("meta") or {}
    assert meta.get("planner", {}).get("planner_rule_id") == "fs_create"
    assert meta.get("executor", {}).get("ok") is True


def test_pipeline_executes_with_local_transport(monkeypatch, tmp_path):
    from core.pipeline import build_local_pipeline
    from resolver.resolver import ResolverConfig

    resolver_cfg = ResolverConfig(
        whitelist=list(capp._WHITELIST_RESOLVER),
        remote_url=None,
        mode="quick",
    )
    pipeline = build_local_pipeline(
        resolver_config=resolver_cfg,
        planner_rules_path=capp._planner_rules_path,
        toolrunner_config={"paths": {"workspace": str(tmp_path)}},
        strict_acl=True,
    )
    monkeypatch.setattr(capp, "_pipeline", pipeline)
    monkeypatch.setattr(capp, "_planner_enabled", True)
    monkeypatch.setattr(capp, "_workspace_root", str(tmp_path))

    client = TestClient(app)
    r = client.post("/chat", json={"text": "создай файл alpha.txt с содержимым тест"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "command"
    assert data["ok"] is True
    assert data["command"] == "files.create"
    assert (tmp_path / "alpha.txt").read_text(encoding="utf-8") == "тест"
    meta = data.get("meta") or {}
    assert meta.get("planner", {}).get("planner_rule_id") == "fs_create"
    assert meta.get("executor", {}).get("ok") is True

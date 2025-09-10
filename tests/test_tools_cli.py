import pytest
from tools_cli import jarvis_cli


def test_run_once_no_exec(monkeypatch, tmp_path):
    cfg = {
        "controller": {"base_url": "http://dummy", "timeout_sec": 1},
        "toolrunner": {"base_url": "http://dummy", "timeout_sec": 1},
        "ui": {"log_file": str(tmp_path / "cli.log"), "history_file": str(tmp_path / "hist.txt")},
    }

    class DummySpinner:
        def __init__(self, enabled):
            pass
        def start(self, label=""):
            pass
        def stop(self):
            pass

    monkeypatch.setattr(jarvis_cli, "Spinner", DummySpinner)

    def fake_chat(cfg, text):
        return 200, {"type": "command", "command": "files.read", "args": {"path": "a.txt"}}, {}, 0.0

    monkeypatch.setattr(jarvis_cli, "do_chat", fake_chat)

    def fake_execute(cfg, cmd, args):
        pytest.fail("execute should not be called")

    monkeypatch.setattr(jarvis_cli, "do_execute", fake_execute)

    captured = {}

    def fake_printer(mode, resp):
        captured["resp"] = resp
        return 0

    monkeypatch.setattr(jarvis_cli, "printer", fake_printer)

    code = jarvis_cli.run_once(cfg, "прочитай", mode="json", no_exec=True)
    assert code == 0
    assert captured["resp"]["type"] == "command"
    assert captured["resp"]["command"] == "files.read"
    assert captured["resp"]["ok"] is None


def test_do_diagnostics(monkeypatch):
    cfg = {"controller": {"base_url": "http://dummy", "timeout_sec": 1}, "ui": {}}

    class DummySpinner:
        def __init__(self, enabled):
            pass
        def start(self, label=""):
            pass
        def stop(self):
            pass

    monkeypatch.setattr(jarvis_cli, "Spinner", DummySpinner)

    def fake_get(url, timeout, headers=None):
        assert url == "http://dummy/diagnostics"
        return 200, {"ok": True}, {}, 0.0

    monkeypatch.setattr(jarvis_cli, "http_get_json", fake_get)

    captured = {}

    def fake_printer(mode, resp):
        captured["resp"] = resp
        return 0

    monkeypatch.setattr(jarvis_cli, "printer", fake_printer)

    code = jarvis_cli.do_diagnostics(cfg, "json")
    assert code == 0
    assert captured["resp"] == {"ok": True}

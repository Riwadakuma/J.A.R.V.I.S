import sys
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


def test_main_diagnostics_success(monkeypatch):
    """jarvis_cli.main exits with 0 when diagnostics succeed."""
    monkeypatch.setattr(sys, "argv", ["jarvis", "--diagnostics"])
    monkeypatch.setattr(jarvis_cli, "load_cfg", lambda path=None: {})
    called = {}

    def fake_diag(cfg):
        called["called"] = True
        return 200, {"ok": True}, {}, 0.0

    monkeypatch.setattr(jarvis_cli, "do_diagnostics", fake_diag, raising=False)
    monkeypatch.setattr(jarvis_cli, "printer", lambda mode, resp: 0)

    with pytest.raises(SystemExit) as exc:
        jarvis_cli.main()

    assert exc.value.code == 0
    assert called["called"]


def test_main_diagnostics_error(monkeypatch):
    """jarvis_cli.main exits with 1 when diagnostics fail."""
    monkeypatch.setattr(sys, "argv", ["jarvis", "--diagnostics"])
    monkeypatch.setattr(jarvis_cli, "load_cfg", lambda path=None: {})

    def fake_diag(cfg):
        return 500, {"detail": "boom"}, {}, 0.0

    monkeypatch.setattr(jarvis_cli, "do_diagnostics", fake_diag, raising=False)
    monkeypatch.setattr(jarvis_cli, "printer", lambda mode, resp: 0)

    with pytest.raises(SystemExit) as exc:
        jarvis_cli.main()

    assert exc.value.code == 1


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

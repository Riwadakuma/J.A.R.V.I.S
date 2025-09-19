import tools_cli.jarvis_cli as jarvis_cli


def test_run_once_prints_preview(monkeypatch, capsys):
    cfg = {
        "controller": {"base_url": "http://dummy", "timeout_sec": 1},
        "toolrunner": {"base_url": "http://dummy", "timeout_sec": 1},
        "ui": {"spinner": False},
    }

    class DummySpinner:
        def __init__(self, enabled):
            pass

        def start(self, label=""):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(jarvis_cli, "Spinner", DummySpinner)
    monkeypatch.setattr(jarvis_cli, "say_key", lambda key, **params: f"say:{key}")
    monkeypatch.setattr(jarvis_cli, "say", lambda text, **params: text or "")

    def fake_chat(cfg, text):
        body = {
            "type": "command",
            "command": "files.create",
            "args": {"path": "demo.txt", "content": "hi"},
            "meta": {
                "planner": {"stylist": {"preview": "planner.preview.files.create"}},
                "resolver": {"confidence": 0.9},
            },
        }
        return 200, body, {}, 0.0

    monkeypatch.setattr(jarvis_cli, "do_chat", fake_chat)

    def fake_execute(cfg, command, args):
        return 200, {"ok": True, "result": "done", "error": None}, {}, 0.0

    monkeypatch.setattr(jarvis_cli, "do_execute", fake_execute)

    exit_code = jarvis_cli.run_once(cfg, "создай", mode="pretty")
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "say:planner.preview.files.create" in captured.out
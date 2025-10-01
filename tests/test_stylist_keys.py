from pathlib import Path

from interaction.stylist import Stylist


def test_required_keys_exist():
    stylist = Stylist(templates_path=Path("interaction/stylist/templates.yaml"))
    for key in [
        "planner.confirm.write",
        "planner.preview.files.create",
        "planner.preview.system.config_set",
        "notify.task.start",
        "presence.online",
        "health.ok",
        "errors.acl",
        "provenance.summary",
    ]:
        rendered = stylist.say_key(key, command="files.create", title="demo", ms=10, status="ok")
        assert isinstance(rendered, str)
        assert rendered


def test_anti_repeat_prevents_duplicate_phrases():
    stylist = Stylist(
        templates={"status.ok": ["первый", "второй", "третий"]},
        history_size=2,
    )
    first = stylist.say_key("status.ok")
    second = stylist.say_key("status.ok")
    assert first != second
    
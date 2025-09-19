from pathlib import Path

from planner.planner import Planner
from resolver.intents import command_intent


RULES_PATH = Path("planner/rules.yaml")


def test_planner_creates_single_step_plan():
    planner = Planner(RULES_PATH)
    intent = command_intent("files.create", args={"path": "demo.txt", "content": "hi"})
    plan = planner.plan(intent)
    assert plan.is_valid
    assert plan.policy.confirmation_level == 1
    assert plan.required_tools == ("files.create",)
    assert plan.provenance["planner_rule_id"] == "fs_create"


def test_planner_handles_unknown_command():
    planner = Planner(RULES_PATH)
    intent = command_intent("unknown.cmd", args={})
    plan = planner.plan(intent)
    assert not plan.is_valid
    assert plan.error == "E_NO_RULE"
from __future__ import annotations

from interaction.resolver.intents import command_intent
from interaction.resolver.legacy_router import legacy_route
from core.controller import app as controller_app
from core.executor.executor import Executor
from core.executor.transports import LocalToolTransport
from toolrunner.management.planner.planner import Plan, PlanStep
from toolrunner.management.planner.policies import PlanPolicy
from toolrunner.tools.management import cmd_management_execute


def test_management_command_executes_via_toolrunner(tmp_path):
    config = {"management": {"db_path": str(tmp_path / "mgmt.sqlite")}}

    created = cmd_management_execute(
        {
            "action": "create_task",
            "title": "Demo",
            "description": "integration",
            "priority": "P2",
        },
        config,
    )
    assert created["success"] is True
    task = created["result"]
    assert task["title"] == "Demo"

    started = cmd_management_execute({"action": "start_task", "task_id": task["id"]}, config)
    assert started["success"] is True
    assert started["result"]["message"] == "Task started"


def test_local_pipeline_runs_management_step(tmp_path):
    config = {"management": {"db_path": str(tmp_path / "pipeline.sqlite")}}
    transport = LocalToolTransport(config)
    executor = Executor(transport)

    intent = command_intent("management.execute", args={"action": "create_task", "title": "ViaPlan"})
    plan = Plan(
        "plan-management",
        intent,
        steps=(
            PlanStep(
                "dispatch",
                "management.execute",
                {"action": "create_task", "title": "ViaPlan", "priority": "P1"},
            ),
        ),
        required_tools=("management.execute",),
        policy=PlanPolicy(acl_tags=("management",)),
        stylist_keys={},
        provenance={},
    )

    result = executor.execute(plan)
    assert result.ok is True
    assert result.result["action"] == "create_task"
    assert result.events[0].tool == "management.execute"


def test_legacy_router_parses_management_command():
    intent = legacy_route("менеджмент start_task task_id=7")
    assert intent.is_command()
    assert intent.name == "management.execute"
    assert intent.args["action"] == "start_task"
    assert intent.args["task_id"] == "7"

    quick = controller_app._ru_quick_intent("управление complete_task task_id=9")
    assert quick is not None
    assert quick["command"] == "management.execute"
    assert quick["args"]["action"] == "complete_task"
    assert quick["args"]["task_id"] == "9"
from pathlib import Path

from executor.executor import Executor
from executor.transports import LocalToolTransport
from planner.planner import Plan, PlanStep
from planner.policies import PlanPolicy
from resolver.intents import command_intent


def make_plan(intent_name: str, args: dict, rule_id: str, confirmation_level: int, acl: tuple[str, ...]):
    intent = command_intent(intent_name, args=args)
    step = PlanStep("s1", tool=intent_name, args=args, on_error=None)
    policy = PlanPolicy(acl_tags=acl, confirmation_level=confirmation_level)
    provenance = {"planner_rule_id": rule_id}
    stylist_keys = {}
    return Plan(
        plan_id="p-1",
        intent=intent,
        steps=(step,),
        required_tools=(intent_name,),
        policy=policy,
        stylist_keys=stylist_keys,
        provenance=provenance,
        error=None,
    )


def test_executor_writes_file(tmp_path):
    plan = make_plan(
        "files.create",
        {"path": "sample.txt", "content": "hello"},
        rule_id="fs_create",
        confirmation_level=1,
        acl=("fs.write",),
    )
    transport = LocalToolTransport({"paths": {"workspace": str(tmp_path)}})
    executor = Executor(transport, strict_acl=True)
    result = executor.execute(plan)
    assert result.ok
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "hello"


def test_executor_denies_acl(tmp_path):
    plan = make_plan(
        "files.create",
        {"path": "fail.txt", "content": "no"},
        rule_id="fs_create",
        confirmation_level=1,
        acl=("fs.read",),
    )
    transport = LocalToolTransport({"paths": {"workspace": str(tmp_path)}})
    executor = Executor(transport, strict_acl=True)
    result = executor.execute(plan)
    assert not result.ok
    assert "E_ACL_DENY" in result.errors[0]
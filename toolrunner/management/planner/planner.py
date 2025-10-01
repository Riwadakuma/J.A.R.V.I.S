"""Rule-based planner that turns intents into executable plans."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

from resolver.intents import Intent

from .policies import PlanPolicy, build_policy


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool: str
    args: Mapping[str, Any]
    on_error: str | None = None


@dataclass(frozen=True)
class Plan:
    plan_id: str
    intent: Intent
    steps: Tuple[PlanStep, ...]
    required_tools: Tuple[str, ...]
    policy: PlanPolicy
    stylist_keys: Dict[str, str]
    provenance: Dict[str, Any]
    error: str | None = None

    def requires_confirmation(self, provided_level: int) -> bool:
        return self.policy.requires_confirmation(provided_level)

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.steps)


class Planner:
    def __init__(self, rules_path: Path) -> None:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("Planner rules must be a mapping")
        self._version = int(data.get("version", 1))
        self._rules: Dict[str, dict] = {
            str(name): spec for name, spec in (data.get("commands") or {}).items()
        }

    def plan(self, intent: Intent, *, context: Optional[Mapping[str, Any]] = None) -> Plan:
        context = context or {}
        plan_id = f"plan-{uuid.uuid4()}"

        if not intent.is_command() or not intent.name:
            provenance = {"planner_rule_id": None, "reason": "not_command"}
            return Plan(
                plan_id,
                intent,
                tuple(),
                tuple(),
                PlanPolicy(acl_tags=tuple()),
                {},
                provenance,
                error="E_NOT_COMMAND",
            )

        rule = self._rules.get(intent.name)
        if not rule:
            provenance = {"planner_rule_id": None, "reason": "missing_rule", "intent": intent.name}
            return Plan(
                plan_id,
                intent,
                tuple(),
                tuple(),
                PlanPolicy(acl_tags=tuple()),
                {},
                provenance,
                error="E_NO_RULE",
            )

        policy = build_policy(rule)
        steps: list[PlanStep] = []
        for raw_step in rule.get("steps", []):
            tool = raw_step.get("tool")
            if not tool:
                continue
            step_id = str(raw_step.get("id") or f"step{len(steps)+1}")
            if raw_step.get("use_intent_args", False):
                args = dict(intent.args)
            else:
                args = dict(raw_step.get("args") or {})
            steps.append(PlanStep(step_id, tool, args, raw_step.get("on_error")))

        required_tools = tuple(step.tool for step in steps)
        stylist_keys = dict(rule.get("stylist") or {})
        provenance = {
            "planner_rule_id": rule.get("rule_id") or intent.name,
            "acl": list(policy.acl_tags),
            "context": dict(context),
        }

        error = None if steps else "E_EMPTY_PLAN"
        return Plan(
            plan_id,
            intent,
            tuple(steps),
            required_tools,
            policy,
            stylist_keys,
            provenance,
            error=error,
        )

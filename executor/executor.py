"""Executor that runs planner steps using transports."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from planner.planner import Plan

from .registry import get_tool_metadata
from .transports import ToolTransport


@dataclass(frozen=True)
class ExecutionEvent:
    step_id: str
    tool: str
    ok: bool
    ms: float
    result: Any = None
    error: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    result: Any
    events: Tuple[ExecutionEvent, ...]
    provenance: Dict[str, Any]
    errors: Tuple[str, ...]


class Executor:
    def __init__(self, transport: ToolTransport, *, strict_acl: bool = True) -> None:
        self._transport = transport
        self._strict_acl = strict_acl

    def execute(self, plan: Plan) -> ExecutionResult:
        if not plan.is_valid:
            provenance = {"executor": {"reason": plan.error, "planner": plan.provenance}}
            return ExecutionResult(False, None, tuple(), provenance, (plan.error or "E_INVALID_PLAN",))

        events: List[ExecutionEvent] = []
        errors: List[str] = []
        last_result: Any = None

        allowed_tags = set(plan.policy.acl_tags)

        for step in plan.steps:
            meta = get_tool_metadata(step.tool)
            if self._strict_acl and meta and allowed_tags and meta.acl_tag not in allowed_tags:
                err = f"E_ACL_DENY:{step.tool}"
                errors.append(err)
                events.append(ExecutionEvent(step.step_id, step.tool, False, 0.0, error=err))
                break

            started = time.perf_counter()
            response = self._transport.execute(step.tool, step.args)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            events.append(
                ExecutionEvent(
                    step.step_id,
                    step.tool,
                    response.ok,
                    elapsed_ms,
                    result=response.result,
                    error=response.error,
                )
            )
            if not response.ok:
                errors.append(response.error or "E_COMMAND_FAILED")
                if step.on_error != "continue":
                    break
            else:
                last_result = response.result

        success = not errors
        provenance = {
            "executor": {
                "events": [
                    {
                        "step_id": ev.step_id,
                        "tool": ev.tool,
                        "ok": ev.ok,
                        "ms": round(ev.ms, 2),
                        "error": ev.error,
                    }
                    for ev in events
                ],
                "policy": {
                    "acl": list(plan.policy.acl_tags),
                    "confirmation_level": plan.policy.confirmation_level,
                },
            },
            "planner": plan.provenance,
        }
        return ExecutionResult(success, last_result, tuple(events), provenance, tuple(errors))

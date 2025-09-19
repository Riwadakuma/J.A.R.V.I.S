"""Shared pipeline wiring Resolver → Planner → Executor."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from executor.executor import Executor, ExecutionResult
from executor.transports import HttpToolTransport, LocalToolTransport
from planner.planner import Plan, Planner
from resolver.intents import Intent
from resolver.resolver import ResolverConfig, ResolverService


@dataclass(frozen=True)
class PipelineResult:
    intent: Intent
    plan: Plan | None
    execution: ExecutionResult | None

    @property
    def is_command(self) -> bool:
        return self.intent.is_command()

    @property
    def ok(self) -> bool:
        if self.execution:
            return self.execution.ok
        return False


class Pipeline:
    def __init__(self, resolver: ResolverService, planner: Planner, executor: Executor) -> None:
        self._resolver = resolver
        self._planner = planner
        self._executor = executor

    def handle(self, text: str, *, context: Optional[Mapping[str, Any]] = None) -> PipelineResult:
        intent = self._resolver.resolve(text, context=context)
        if not intent.is_command():
            return PipelineResult(intent, None, None)

        plan = self._planner.plan(intent, context=context)
        if not plan.is_valid:
            return PipelineResult(intent, plan, None)

        execution = self._executor.execute(plan)
        return PipelineResult(intent, plan, execution)


def build_http_pipeline(
    *,
    resolver_config: ResolverConfig,
    planner_rules_path: Path,
    toolrunner_url: str,
    toolrunner_timeout: float = 30.0,
    toolrunner_token: str | None = None,
    strict_acl: bool = True,
) -> Pipeline:
    resolver = ResolverService(config=resolver_config)
    planner = Planner(planner_rules_path)
    transport = HttpToolTransport(toolrunner_url, timeout=toolrunner_timeout, token=toolrunner_token)
    executor = Executor(transport, strict_acl=strict_acl)
    return Pipeline(resolver, planner, executor)


def build_local_pipeline(
    *,
    resolver_config: ResolverConfig,
    planner_rules_path: Path,
    toolrunner_config: Mapping[str, Any] | None = None,
    strict_acl: bool = True,
) -> Pipeline:
    resolver = ResolverService(config=resolver_config)
    planner = Planner(planner_rules_path)
    transport = LocalToolTransport(toolrunner_config)
    executor = Executor(transport, strict_acl=strict_acl)
    return Pipeline(resolver, planner, executor)

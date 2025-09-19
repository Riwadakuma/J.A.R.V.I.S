"""Dataclasses that describe resolver output consumed by the planner layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Mapping, MutableMapping

IntentType = Literal["chat", "command"]


@dataclass(frozen=True)
class ResolverMeta:
    """Auxiliary metadata produced by the resolver stage."""

    trace_id: str | None = None
    confidence: float | None = None
    rule: str | None = None
    source: str | None = None
    fallback_used: bool = False
    explain: tuple[str, ...] = tuple()

    def merged_with(self, **updates: Any) -> "ResolverMeta":
        data: MutableMapping[str, Any] = {
            "trace_id": self.trace_id,
            "confidence": self.confidence,
            "rule": self.rule,
            "source": self.source,
            "fallback_used": self.fallback_used,
            "explain": self.explain,
        }
        data.update({k: v for k, v in updates.items() if v is not None})
        explain = data.get("explain")
        if isinstance(explain, list):
            data["explain"] = tuple(explain)
        return ResolverMeta(**data)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Intent:
    """Resolver decision fed into the planner."""

    kind: IntentType
    name: str | None = None
    args: Mapping[str, Any] = field(default_factory=dict)
    text: str | None = None
    meta: ResolverMeta = field(default_factory=ResolverMeta)

    def is_command(self) -> bool:
        return self.kind == "command" and bool(self.name)

    def asdict(self) -> Dict[str, Any]:
        return {
            "type": self.kind,
            "name": self.name,
            "args": dict(self.args),
            "text": self.text,
            "meta": {
                "trace_id": self.meta.trace_id,
                "confidence": self.meta.confidence,
                "rule": self.meta.rule,
                "source": self.meta.source,
                "fallback_used": self.meta.fallback_used,
                "explain": list(self.meta.explain),
            },
        }


def command_intent(
    name: str,
    *,
    args: Mapping[str, Any] | None = None,
    confidence: float | None = None,
    rule: str | None = None,
    trace_id: str | None = None,
    source: str | None = None,
    fallback_used: bool = False,
    explain: tuple[str, ...] | list[str] | None = None,
) -> Intent:
    meta = ResolverMeta(
        trace_id=trace_id,
        confidence=confidence,
        rule=rule,
        source=source,
        fallback_used=fallback_used,
        explain=tuple(explain or ()),
    )
    return Intent("command", name=name, args=args or {}, meta=meta)


def chat_intent(
    text: str,
    *,
    rule: str | None = None,
    trace_id: str | None = None,
    explain: tuple[str, ...] | list[str] | None = None,
) -> Intent:
    meta = ResolverMeta(trace_id=trace_id, rule=rule, explain=tuple(explain or ()))
    return Intent("chat", text=text, meta=meta)

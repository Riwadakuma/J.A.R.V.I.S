"""Resolver service that unifies quick rules, legacy router and remote resolver."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import httpx

from .intents import Intent, chat_intent, command_intent
from .legacy_router import ALLOWED as LEGACY_ALLOWED, legacy_route
from .rules_quick import resolve_quick


@dataclass
class ResolverConfig:
    whitelist: Sequence[str] = tuple(LEGACY_ALLOWED)
    remote_url: str | None = None
    timeout: float = 2.5
    mode: str = "hybrid"  # quick | hybrid | remote
    low_conf_threshold: float = 0.5
    use_legacy_when_low_conf: bool = True
    llm_threshold: float = 0.75
    llm_enable: bool = True
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "tinyllama"

    def to_payload(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "llm_threshold": self.llm_threshold,
            "llm": {
                "enable": self.llm_enable,
                "base_url": self.llm_base_url,
                "model": self.llm_model,
            },
        }


class ResolverService:
    def __init__(
        self,
        *,
        config: ResolverConfig,
        http_client_cls: type[httpx.Client] = httpx.Client,
    ) -> None:
        self._cfg = config
        self._http_client_cls = http_client_cls
        self._whitelist = set(config.whitelist or LEGACY_ALLOWED)

    def resolve(self, text: str, *, context: Optional[Mapping[str, Any]] = None) -> Intent:
        trace_id = str(uuid.uuid4())
        context = context or {}

        quick = resolve_quick(text)
        if quick and quick.name in self._whitelist:
            return command_intent(
                quick.name,
                args=quick.args,
                confidence=0.99,
                rule=quick.meta.rule or "quick",
                trace_id=trace_id,
                source=quick.meta.source or "quick",
                explain=quick.meta.explain,
            )

        remote_chat: Optional[Intent] = None
        if self._cfg.remote_url and self._cfg.mode in {"hybrid", "remote"}:
            remote_intent = self._resolve_remote(text, context=context, trace_id=trace_id)
            if remote_intent and remote_intent.is_command():
                if remote_intent.meta.confidence is None:
                    return remote_intent
                if (
                    self._cfg.use_legacy_when_low_conf
                    and remote_intent.meta.confidence < self._cfg.low_conf_threshold
                ):
                    # keep provenance but fall back to legacy routing for actual command
                    fallback = legacy_route(text)
                    if fallback.is_command():
                        return command_intent(
                            fallback.name or "",
                            args=fallback.args,
                            confidence=remote_intent.meta.confidence,
                            rule=fallback.meta.rule,
                            trace_id=trace_id,
                            source=fallback.meta.source or "legacy",
                            fallback_used=True,
                            explain=fallback.meta.explain,
                        )
                    return remote_intent
                return remote_intent
            if remote_intent:
                remote_chat = remote_intent

        # final fallback – legacy router
        legacy_intent = legacy_route(text)
        if legacy_intent.is_command() and (legacy_intent.name in self._whitelist):
            return command_intent(
                legacy_intent.name or "",
                args=legacy_intent.args,
                confidence=0.49,
                rule=legacy_intent.meta.rule,
                trace_id=trace_id,
                source=legacy_intent.meta.source or "legacy",
                fallback_used=True,
                explain=legacy_intent.meta.explain,
            )
        if remote_chat and not remote_chat.is_command():
            return remote_chat
        return chat_intent(text, trace_id=trace_id, rule="chat")

    # ------------------------------------------------------------------
    def _resolve_remote(
        self,
        text: str,
        *,
        context: Mapping[str, Any],
        trace_id: str,
    ) -> Optional[Intent]:
        payload = {
            "trace_id": trace_id,
            "text": text,
            "context": dict(context),
            "constraints": {"whitelist": sorted(self._whitelist)},
            "config": self._cfg.to_payload(),
        }
        try:
            with self._http_client_cls(timeout=self._cfg.timeout) as client:
                response = client.post(f"{self._cfg.remote_url.rstrip('/')}/resolve", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            explain = [f"remote_error:{exc}"]
            return chat_intent(text, trace_id=trace_id, rule="remote_error", explain=explain)

        command = data.get("command")
        args = data.get("args") or {}
        confidence = self._safe_float(data.get("confidence"))
        fallback_used = bool(data.get("fallback_used", False))
        explain = tuple(str(x) for x in (data.get("explain") or []))

        if command and command in self._whitelist:
            return command_intent(
                command,
                args=args,
                confidence=confidence,
                rule=str(data.get("resolver_rule") or "remote"),
                trace_id=trace_id,
                source="remote",
                fallback_used=fallback_used,
                explain=explain,
            )

        if fallback_used and command in self._whitelist:
            return command_intent(
                command,
                args=args,
                confidence=confidence,
                rule="remote_fallback",
                trace_id=trace_id,
                source="remote",
                fallback_used=True,
                explain=explain,
            )

        return chat_intent(text, trace_id=trace_id, rule="remote_unhandled", explain=explain)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

"""Tool execution transports used by the executor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from toolrunner import registry as tr_registry
from toolrunner import security as tr_security


@dataclass(frozen=True)
class TransportResponse:
    ok: bool
    result: Any = None
    error: str | None = None
    raw: Any = None


class ToolTransport(Protocol):
    def execute(self, tool: str, args: Mapping[str, Any]) -> TransportResponse:
        """Execute `tool` with `args` and return a structured response."""


class HttpToolTransport:
    def __init__(self, base_url: str, *, timeout: float = 30.0, token: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._token = token

    def execute(self, tool: str, args: Mapping[str, Any]) -> TransportResponse:
        payload = {"command": tool, "args": dict(args)}
        headers = {"X-Jarvis-Token": self._token} if self._token else {}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._base}/execute", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return TransportResponse(ok=False, error=f"E_HTTP:{exc}")

        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail") if isinstance(body, dict) else None
            except ValueError:
                detail = response.text
            return TransportResponse(ok=False, error=str(detail or "E_COMMAND_FAILED"), raw=response)

        try:
            body = response.json()
        except ValueError as exc:
            return TransportResponse(ok=False, error=f"E_BAD_RESPONSE:{exc}", raw=response)

        return TransportResponse(
            ok=bool(body.get("ok", True)),
            result=body.get("result"),
            error=body.get("error"),
            raw=body,
        )


class LocalToolTransport:
    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self._config = dict(config or {})
        self._registry = dict(tr_registry.REGISTRY)

    def execute(self, tool: str, args: Mapping[str, Any]) -> TransportResponse:
        handler = self._registry.get(tool)
        if not handler:
            return TransportResponse(ok=False, error="E_UNKNOWN_COMMAND")
        normalized = tr_security.normalize_args(dict(args))
        try:
            result = handler(normalized, self._config)
            return TransportResponse(ok=True, result=result)
        except Exception as exc:
            msg = str(exc)
            if msg.startswith("E_"):
                return TransportResponse(ok=False, error=msg)
            return TransportResponse(ok=False, error=f"E_RUNTIME:{exc}")

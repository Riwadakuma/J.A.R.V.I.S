"""Utilities for formatting CLI log entries in a human-friendly way."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
import json


def _truncate(text: str, limit: int = 160) -> str:
    """Return ``text`` limited to ``limit`` characters with ellipsis when needed."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _clean(text: str) -> str:
    """Collapse whitespace in ``text`` so log lines remain compact."""
    return " ".join(text.split())


def _summarise_body(body: Any) -> str:
    if isinstance(body, dict):
        body_type = body.get("type")
        if body_type == "chat":
            text = _clean(str(body.get("text", "")))
            return f"type=chat text=\"{_truncate(text, 100)}\""
        if body_type == "command":
            cmd = body.get("command") or ""
            ok = body.get("ok")
            error = body.get("error")
            if ok is None:
                return f"type=command command={cmd} pending"
            if ok:
                result = body.get("result")
                if isinstance(result, str):
                    return (
                        f"type=command command={cmd} ok result=\"{_truncate(_clean(result), 80)}\""
                    )
                if result is None:
                    return f"type=command command={cmd} ok"
                if isinstance(result, list):
                    return f"type=command command={cmd} ok list[{len(result)}]"
                return f"type=command command={cmd} ok result_type={type(result).__name__}"
            detail = error or body.get("detail")
            if detail:
                return f"type=command command={cmd} error={_truncate(_clean(str(detail)), 80)}"
            return f"type=command command={cmd} error"
        if "detail" in body:
            return f"detail=\"{_truncate(_clean(str(body['detail'])), 100)}\""
        return _truncate(json.dumps(body, ensure_ascii=False), 120)
    if isinstance(body, list):
        return f"list[{len(body)}]"
    if body is None:
        return "body=None"
    return _truncate(json.dumps(body, ensure_ascii=False), 120)


def _format_response(payload: Dict[str, Any]) -> str:
    status = payload.get("status")
    ms = payload.get("ms")
    summary = _summarise_body(payload.get("body"))
    parts = [f"status={status}"] if status is not None else []
    if ms is not None:
        parts.append(f"ms={ms}")
    parts.append(summary)
    return " ".join(parts)


def _format_cli_input(payload: Dict[str, Any]) -> str:
    text = _truncate(_clean(str(payload.get("text", ""))), 120)
    mode = payload.get("mode") or "pretty"
    no_exec = bool(payload.get("no_exec"))
    verbose = payload.get("verbose")
    parts = [f'text="{text}"', f"mode={mode}", f"no_exec={'yes' if no_exec else 'no'}"]
    if verbose:
        parts.append(f"verbose={verbose}")
    source = payload.get("source")
    if source:
        parts.append(f"source={source}")
    return " ".join(parts)


def _format_default(payload: Dict[str, Any]) -> str:
    return _truncate(json.dumps(payload, ensure_ascii=False, sort_keys=True), 160)


_FORMATTERS = {
    "cli_input": _format_cli_input,
    "chat_response": _format_response,
    "execute_response": _format_response,
    "diagnostics_response": _format_response,
}


def format_cli_event(event: str, payload: Dict[str, Any]) -> str:
    """Return a single formatted log line for the CLI log file."""

    formatter = _FORMATTERS.get(event, _format_default)
    line = formatter(payload or {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{ts} | {event:<18} | {line}"
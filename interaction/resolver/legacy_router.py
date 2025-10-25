"""Legacy pattern-based router kept for backwards compatibility."""
from __future__ import annotations

import re
import shlex
from typing import Any, Dict

from .intents import Intent, command_intent, chat_intent

ALLOWED = {
    "files.list",
    "files.read",
    "files.create",
    "files.append",
    "files.open",
    "files.reveal",
    "files.shortcut_to_desktop",
    "system.help",
    "system.config_get",
    "system.config_set",
    "management.execute",
}

_PATTERNS = [
    (r'^\s*файлы\s+"([^"]+)"\s*$', lambda m: ("files.list", {"mask": m.group(1)})),
    (r'^\s*прочитай\s+"([^"]+)"\s*$', lambda m: ("files.read", {"path": m.group(1)})),
    (
        r'^\s*создай\s+файл\s+"([^"]+)"\s+с\s+содержимым\s+(.+)\s*$',
        lambda m: ("files.create", {"path": m.group(1), "content": m.group(2)}),
    ),
    (
        r'^\s*допиши\s+в\s+"([^"]+)"\s+текст\s+(.+)\s*$',
        lambda m: ("files.append", {"path": m.group(1), "content": m.group(2)}),
    ),
    (r'^\s*открой\s+"([^"]+)"\s*$', lambda m: ("files.open", {"path": m.group(1)})),
    (r'^\s*покажи\s+"([^"]+)"\s*$', lambda m: ("files.reveal", {"path": m.group(1)})),
    (r'^\s*ярлык\s+"([^"]+)"\s*$', lambda m: ("files.shortcut_to_desktop", {"path": m.group(1)})),
    (r'^\s*помощь\s*$', lambda m: ("system.help", {})),
    (r'^\s*конфиг\s+показать\s*$', lambda m: ("system.config_get", {})),
    (
        r'^\s*конфиг\s+установить\s+(\S+)\s+(.+)\s*$',
        lambda m: ("system.config_set", {"key": m.group(1), "value": m.group(2)}),
    ),
    (
        r'^\s*(?:менеджмент|управление)\s+(\w+)(?:\s+(.*))?\s*$',
        lambda m: ("management.execute", {"action": m.group(1), "_extra": m.group(2) or ""}),
    ),
]


def _normalize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (args or {}).items():
        if isinstance(value, str):
            out[key] = value.strip().strip('"').strip("'")
        else:
            out[key] = value
    return out


def _parse_management_args(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    tokens = shlex.split(raw)
    args: Dict[str, Any] = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError("E_INVALID_MANAGEMENT_ARGS")
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("E_INVALID_MANAGEMENT_ARGS")
        args[key] = value.strip()
    return args


def legacy_route(text: str) -> Intent:
    stripped = text.strip()
    for pattern, builder in _PATTERNS:
        match = re.match(pattern, stripped, flags=re.IGNORECASE)
        if not match:
            continue
        command, args = builder(match)
        if command in ALLOWED:
            payload = dict(args)
            if command == "management.execute":
                action = payload.get("action", "").strip()
                if not action:
                    continue
                try:
                    extras = _parse_management_args(payload.get("_extra", ""))
                except ValueError:
                    continue
                payload = {"action": action, **extras}
            return command_intent(
                command,
                args=_normalize_args(payload),
                rule="legacy_router",
                source="legacy",
            )
    return chat_intent(stripped or "", rule="legacy_router", explain=["no_match"])

"""Lightweight intent resolver based on handwritten regex rules."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

from .intents import Intent, command_intent

_clean_replacements = str.maketrans({
    "“": '"',
    "”": '"',
    "«": '"',
    "»": '"',
    "‘": "'",
    "’": "'",
})


def _clean_str(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip().translate(_clean_replacements)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    text = text.replace("\\\\", "\\")
    return text


def _build_command(cmd: str, **args: Any) -> Intent:
    clean_args = {k: _clean_str(v) for k, v in args.items() if v is not None}
    return command_intent(cmd, args=clean_args, rule="quick_ru", source="quick")


_PATTERN_BUILDERS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], Intent | None]], ...] = (
    (
        re.compile(r"^(?:создай|создать)\s+файл\s+(.+?)\s+с\s+содержимым\s+(.+)$", re.IGNORECASE),
        lambda m: _build_command("files.create", path=m.group(1), content=m.group(2)),
    ),
    (
        re.compile(r"^(?:создай|создать)\s+файл\s+(.+)$", re.IGNORECASE),
        lambda m: _build_command("files.create", path=m.group(1), content=""),
    ),
    (
        re.compile(r"^(?:прочитай|прочитать)\s+файл\s+(.+)$", re.IGNORECASE),
        lambda m: _build_command("files.read", path=m.group(1)),
    ),
    (
        re.compile(r"^(?:покажи|список|файлы)(?:\s+(.*))?$", re.IGNORECASE),
        lambda m: _build_command("files.list", mask=m.group(1) or "*"),
    ),
    (
        re.compile(r"^(?:открой|открыть)\s+файл\s+(.+)$", re.IGNORECASE),
        lambda m: _build_command("files.open", path=m.group(1)),
    ),
    (
        re.compile(r"^(?:допиши|добавь)\s+в\s+файл\s+(.+?)\s*[:\-–]\s*(.+)$", re.IGNORECASE),
        lambda m: _build_command("files.append", path=m.group(1), content=m.group(2)),
    ),
    (
        re.compile(r"^помощь\s*$", re.IGNORECASE),
        lambda m: _build_command("system.help"),
    ),
    (
        re.compile(r"^конфиг\s+показать\s*$", re.IGNORECASE),
        lambda m: _build_command("system.config_get"),
    ),
    (
        re.compile(r"^конфиг\s+установить\s+(\S+)\s+(.+)$", re.IGNORECASE),
        lambda m: _build_command("system.config_set", key=m.group(1), value=m.group(2)),
    ),
)


def resolve_quick(text: str) -> Optional[Intent]:
    """Try to resolve `text` using quick regex patterns."""

    stripped = text.strip()
    if not stripped:
        return None
    for pattern, builder in _PATTERN_BUILDERS:
        match = pattern.match(stripped)
        if not match:
            continue
        intent = builder(match)
        if intent and intent.is_command():
            return intent
    return None

"""Styling helpers ensuring Jarvis speaks with a consistent voice."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

import yaml

__all__ = ["Stylist", "get_stylist", "say", "say_key"]


@dataclass(frozen=True)
class _Variant:
    text: str
    weight: float = 1.0


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover - simple passthrough
        return "{" + key + "}"


class Stylist:
    """Template-based phrase selector with repetition control and filtering."""

    _DEFAULT_REPLACEMENTS = {
        "ок": "принято",
        "окей": "принято",
        "ладно": "хорошо",
    }
    _OPENING_PATTERN = re.compile(r"^(?:ну|ладно|окей|ок)[\s,–-]+", re.IGNORECASE)

    def __init__(
        self,
        templates: Optional[Mapping[str, Any]] = None,
        *,
        templates_path: Optional[Path] = None,
        history_size: int = 4,
        replacements: Optional[Mapping[str, str]] = None,
        randomizer: Optional[random.Random] = None,
    ) -> None:
        self._history_size = max(1, history_size)
        self._history: Dict[str, List[str]] = {}
        self._random = randomizer or random.Random()
        self._defaults: Dict[str, Any] = {
            "signature": "командир",
            "signature_short": "сэр",
            "broken": "",
        }
        repl = dict(self._DEFAULT_REPLACEMENTS)
        if replacements:
            repl.update(replacements)
        self._replacement_rules = [
            (re.compile(rf"\b{re.escape(src)}\b", re.IGNORECASE), dst)
            for src, dst in repl.items()
        ]
        if templates is not None:
            data = templates
        else:
            path = templates_path or Path(__file__).parent / "templates.yaml"
            if not path.exists():
                data = {}
            else:
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
                data = loaded or {}
        self._templates = self._flatten_templates(data)

    # --------------------------- public API ---------------------------
    def update_defaults(self, **values: Any) -> None:
        """Update default placeholder values used during formatting."""

        for key, value in values.items():
            if value is not None:
                self._defaults[key] = value

    def say(self, text: Optional[str], **params: Any) -> str:
        """Filter arbitrary ``text`` and return a stylised phrase."""

        if not text:
            return ""
        formatted = self._format(text, params)
        return self._apply_filters(formatted)

    def say_key(self, key: str, **params: Any) -> str:
        """Render a template by ``key`` applying anti-repetition safeguards."""

        variants = self._templates.get(key)
        if not variants:
            return self.say(key, **params)
        history = self._history.setdefault(key, [])
        pool = [v for v in variants if v.text not in history]
        if not pool:
            history.clear()
            pool = list(variants)
        weights = [v.weight for v in pool]
        chosen = self._random.choices(pool, weights=weights, k=1)[0]
        history.append(chosen.text)
        if len(history) > self._history_size:
            del history[0 : len(history) - self._history_size]
        formatted = self._format(chosen.text, params)
        return self._apply_filters(formatted)

    # --------------------------- helpers ---------------------------
    def _flatten_templates(self, data: Mapping[str, Any]) -> Dict[str, List[_Variant]]:
        flattened: Dict[str, List[_Variant]] = {}

        def walk(prefix: str, node: Any) -> None:
            if isinstance(node, Mapping):
                for key, value in node.items():
                    next_prefix = f"{prefix}.{key}" if prefix else str(key)
                    walk(next_prefix, value)
            elif isinstance(node, Iterable) and not isinstance(node, (str, bytes)):
                variants: List[_Variant] = []
                for item in node:
                    if isinstance(item, Mapping):
                        text = str(item.get("text", ""))
                        weight = float(item.get("weight", 1.0) or 1.0)
                    else:
                        text = str(item)
                        weight = 1.0
                    if text:
                        variants.append(_Variant(text=text, weight=weight))
                if variants:
                    flattened[prefix] = variants
            elif node:
                flattened[prefix] = [_Variant(text=str(node), weight=1.0)]

        walk("", data)
        return flattened

    def _format(self, template: str, params: Mapping[str, Any]) -> str:
        ctx: MutableMapping[str, Any] = _SafeDict(self._defaults.copy())
        for key, value in params.items():
            ctx[key] = value
        return template.format_map(ctx)

    def _apply_filters(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        text = self._OPENING_PATTERN.sub("", text).lstrip()
        for rx, replacement in self._replacement_rules:
            text = rx.sub(lambda m, repl=replacement: self._match_case(repl, m.group(0)), text)
        text = text.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")
        text = re.sub(r" {2,}", " ", text)
        if text and text[0].isalpha():
            text = text[0].upper() + text[1:]
        return text

    @staticmethod
    def _match_case(template: str, sample: str) -> str:
        if sample.isupper():
            return template.upper()
        if sample[:1].isupper():
            return template.capitalize()
        return template


_default_stylist = Stylist()


def get_stylist() -> Stylist:
    """Return the global Stylist instance."""

    return _default_stylist


def say(text: Optional[str], **params: Any) -> str:
    """Filter arbitrary ``text`` through the global stylist."""

    return _default_stylist.say(text, **params)


def say_key(key: str, **params: Any) -> str:
    """Render ``key`` template via the global stylist."""

    return _default_stylist.say_key(key, **params)
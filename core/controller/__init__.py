"""Controller package helpers."""

from importlib import import_module
from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        module = import_module("controller.app")
        return module.app
    raise AttributeError(name)
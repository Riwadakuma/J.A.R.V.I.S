"""Planner policies covering ACL and confirmation rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class PlanPolicy:
    acl_tags: Tuple[str, ...]
    confirmation_level: int = 0
    confirmation_prompt_key: str | None = None

    def requires_confirmation(self, provided_level: int) -> bool:
        return provided_level < self.confirmation_level


def build_policy(data: dict) -> PlanPolicy:
    acl = tuple(str(tag) for tag in data.get("acl", []))
    level = int(data.get("confirmation_level", 0))
    prompt = data.get("stylist", {}).get("confirmation") if isinstance(data.get("stylist"), dict) else None
    return PlanPolicy(acl_tags=acl, confirmation_level=level, confirmation_prompt_key=prompt)

management/constants.py"""Shared constants and enumerations for the management module."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum


class TaskType(str, Enum):
    """Supported categories of tasks."""

    WORK = "work"
    PROJECT = "project"
    PERSONAL = "personal"


class PriorityLevel(str, Enum):
    """Priority ladder used for scheduling and reminder logic."""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class TaskStatus(str, Enum):
    """Lifecycle of a task inside the management module."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DROPPED = "dropped"


class TrustLevel(str, Enum):
    """Visibility level of contacts."""

    U1 = "U1"
    U2 = "U2"
    U3 = "U3"
    U4 = "U4"


class AgentState(str, Enum):
    """Top-level state that drives availability and tone."""

    SLEEP = "SLEEP"
    FOCUS_DEEP = "FOCUS_DEEP"
    FOCUS_LIGHT = "FOCUS_LIGHT"
    GAMING = "GAMING"
    AFK = "AFK"
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class PriorityRule:
    """Configuration describing behaviour for a priority tier."""

    confirmation_level_shift: int
    confirmation_level_delete: int
    reminder_offsets: tuple[timedelta, ...]
    auto_drop_after: timedelta | None = None
    re_evaluate_on_shift: bool = False
    escalate_logs_on_delete: bool = False


DEFAULT_REMINDER_OFFSETS = (timedelta(minutes=-30), timedelta())

PRIORITY_RULES: dict[PriorityLevel, PriorityRule] = {
    PriorityLevel.P1: PriorityRule(
        confirmation_level_shift=0,
        confirmation_level_delete=0,
        reminder_offsets=(timedelta(hours=-4),) + DEFAULT_REMINDER_OFFSETS,
        auto_drop_after=timedelta(days=7),
    ),
    PriorityLevel.P2: PriorityRule(
        confirmation_level_shift=0,
        confirmation_level_delete=0,
        reminder_offsets=(timedelta(hours=-2),) + DEFAULT_REMINDER_OFFSETS,
    ),
    PriorityLevel.P3: PriorityRule(
        confirmation_level_shift=1,
        confirmation_level_delete=1,
        reminder_offsets=(timedelta(hours=-2, minutes=-30),) + DEFAULT_REMINDER_OFFSETS,
        re_evaluate_on_shift=True,
    ),
    PriorityLevel.P4: PriorityRule(
        confirmation_level_shift=1,
        confirmation_level_delete=2,
        reminder_offsets=(timedelta(hours=-2), timedelta(minutes=-10)) + DEFAULT_REMINDER_OFFSETS,
        escalate_logs_on_delete=True,
    ),
}


CAPACITY_LEVELS = {
    "full": 1.0,
    "reduced": 0.75,
    "limited": 0.45,
    "rest": 0.0,
}
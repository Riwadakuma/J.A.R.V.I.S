"""Dataclasses used by the management module."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .constants import AgentState, PriorityLevel, TaskStatus, TaskType, TrustLevel


@dataclass(slots=True)
class TaskRecord:
    """Serializable representation of a task."""

    id: int
    title: str
    description: str | None
    task_type: TaskType
    priority: PriorityLevel
    status: TaskStatus
    start_time: datetime | None
    end_time: datetime | None
    hard_deadline: datetime | None
    soft_deadline: datetime | None
    default_reminder_offset: int
    auto_drop_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    active_session_started_at: datetime | None
    actual_start: datetime | None

    @classmethod
    def from_row(cls, row: Any) -> "TaskRecord":
        return cls(
            id=int(row["id"]),
            title=row["title"],
            description=row["description"],
            task_type=TaskType(row["task_type"]),
            priority=PriorityLevel(row["priority"]),
            status=TaskStatus(row["status"]),
            start_time=_parse_optional(row["start_time"]),
            end_time=_parse_optional(row["end_time"]),
            hard_deadline=_parse_optional(row["hard_deadline"]),
            soft_deadline=_parse_optional(row["soft_deadline"]),
            default_reminder_offset=int(row["default_reminder_offset"]),
            auto_drop_at=_parse_optional(row["auto_drop_at"]),
            created_at=_parse_required(row["created_at"]),
            updated_at=_parse_required(row["updated_at"]),
            completed_at=_parse_optional(row["completed_at"]),
            cancelled_at=_parse_optional(row["cancelled_at"]),
            active_session_started_at=_parse_optional(row["active_session_started_at"]),
            actual_start=_parse_optional(row["actual_start"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "start_time": _format_optional(self.start_time),
            "end_time": _format_optional(self.end_time),
            "hard_deadline": _format_optional(self.hard_deadline),
            "soft_deadline": _format_optional(self.soft_deadline),
            "default_reminder_offset": self.default_reminder_offset,
            "auto_drop_at": _format_optional(self.auto_drop_at),
            "created_at": _format_required(self.created_at),
            "updated_at": _format_required(self.updated_at),
            "completed_at": _format_optional(self.completed_at),
            "cancelled_at": _format_optional(self.cancelled_at),
            "active_session_started_at": _format_optional(self.active_session_started_at),
            "actual_start": _format_optional(self.actual_start),
        }


@dataclass(slots=True)
class EventRecord:
    id: int
    task_id: int | None
    event_type: str
    scheduled_for: datetime
    status: str
    payload: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> "EventRecord":
        return cls(
            id=int(row["id"]),
            task_id=int(row["task_id"]) if row["task_id"] is not None else None,
            event_type=row["event_type"],
            scheduled_for=_parse_required(row["scheduled_for"]),
            status=row["status"],
            payload=_parse_json(row["payload"]),
            created_at=_parse_required(row["created_at"]),
        )


@dataclass(slots=True)
class LogEntry:
    id: int
    timestamp: datetime
    action: str
    task_id: int | None
    contact_id: int | None
    state: AgentState | None
    payload: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: Any) -> "LogEntry":
        return cls(
            id=int(row["id"]),
            timestamp=_parse_required(row["timestamp"]),
            action=row["action"],
            task_id=int(row["task_id"]) if row["task_id"] is not None else None,
            contact_id=int(row["contact_id"]) if row["contact_id"] is not None else None,
            state=AgentState(row["state"]) if row["state"] else None,
            payload=_parse_json(row["payload"]),
        )


@dataclass(slots=True)
class ContactRecord:
    id: int
    name: str
    trust_level: TrustLevel
    details: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: Any) -> "ContactRecord":
        return cls(
            id=int(row["id"]),
            name=row["name"],
            trust_level=TrustLevel(row["trust_level"]),
            details=_parse_json(row["details"]),
        )


@dataclass(slots=True)
class ActionResult:
    """Result of an operation that might require confirmation."""

    success: bool
    message: str
    requires_confirmation: bool = False
    required_level: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Digest:
    """Aggregated statistics for daily or weekly digests."""

    timestamp: datetime
    summary: dict[str, Any]
    recommendations: list[str]


def _parse_required(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _parse_optional(value: Any) -> datetime | None:
    if value is None:
        return None
    return _parse_required(value)


def _parse_json(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    import json

    return json.loads(value)


def _format_optional(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _format_required(value: datetime) -> str:
    return value.isoformat()


__all__ = [
    "TaskRecord",
    "EventRecord",
    "LogEntry",
    "ContactRecord",
    "ActionResult",
    "Digest",
]
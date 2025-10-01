"""High level orchestration for the management module."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from .constants import (
    AgentState,
    PriorityLevel,
    PRIORITY_RULES,
    TaskStatus,
    TaskType,
    TrustLevel,
)
from .database import ManagementDatabase
from .models import ActionResult, ContactRecord, Digest, EventRecord, TaskRecord


@dataclass(slots=True)
class CapacityDecision:
    """Outcome of applying capacity rules."""

    capacity: float
    suggested_drops: list[int]
    required_drops: list[int]
    force_rest: bool


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _to_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _to_enum(value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)


class ManagementService:
    """Implements task, reminder and wellbeing logic."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db = ManagementDatabase(db_path or ":memory:")
        self.current_state = AgentState.OFFLINE
        self._state_row_id: int | None = None
        self._state_started_at: datetime | None = None
        self.capacity: float = 1.0
        self.last_health_check: datetime | None = None
        self.last_emotion_check: datetime | None = None

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------
    def create_task(
        self,
        title: str,
        description: str | None = None,
        *,
        task_type: TaskType | str = TaskType.WORK,
        priority: PriorityLevel | str = PriorityLevel.P3,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        hard_deadline: datetime | str | None = None,
        soft_deadline: datetime | str | None = None,
        default_reminder_offset: int = 30,
    ) -> TaskRecord:
        """Create a task and schedule reminders."""

        task_type = _to_enum(task_type, TaskType)
        priority = _to_enum(priority, PriorityLevel)
        now = _now()
        start_dt = _to_datetime(start_time)
        end_dt = _to_datetime(end_time)
        hard_dt = _to_datetime(hard_deadline)
        soft_dt = _to_datetime(soft_deadline)

        rule = PRIORITY_RULES[priority]
        auto_drop_at = now + rule.auto_drop_after if rule.auto_drop_after else None

        task_id = self.db.insert(
            """
            INSERT INTO tasks (
                title, description, task_type, priority, status, start_time, end_time,
                hard_deadline, soft_deadline, default_reminder_offset, auto_drop_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                task_type.value,
                priority.value,
                TaskStatus.PLANNED.value,
                start_dt.isoformat() if start_dt else None,
                end_dt.isoformat() if end_dt else None,
                hard_dt.isoformat() if hard_dt else None,
                soft_dt.isoformat() if soft_dt else None,
                int(default_reminder_offset),
                auto_drop_at.isoformat() if auto_drop_at else None,
                now.isoformat(),
                now.isoformat(),
            ),
        )

        task = self.get_task(task_id)
        self._schedule_task_reminders(task)
        self._schedule_auto_drop(task)
        self._log("task_created", task_id=task.id, payload=task.to_dict())
        return task

    def get_task(self, task_id: int) -> TaskRecord:
        rows = self.db.query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not rows:
            raise KeyError(f"Task {task_id} not found")
        return TaskRecord.from_row(rows[0])

    def list_tasks(self, *, include_closed: bool = True) -> list[TaskRecord]:
        rows = self.db.query(
            "SELECT * FROM tasks" + ("" if include_closed else " WHERE status NOT IN ('completed','cancelled','dropped')")
        )
        return [TaskRecord.from_row(row) for row in rows]

    def shift_task(
        self,
        task_id: int,
        *,
        new_start: datetime | str | None = None,
        new_end: datetime | str | None = None,
        confirmation_level: int = 0,
    ) -> ActionResult:
        task = self.get_task(task_id)
        rule = PRIORITY_RULES[task.priority]
        required = rule.confirmation_level_shift
        if confirmation_level < required:
            self._log(
                "shift_confirmation_required",
                task_id=task_id,
                payload={"required_level": required, "provided": confirmation_level},
            )
            return ActionResult(
                success=False,
                message="Confirmation required before shifting task",
                requires_confirmation=True,
                required_level=required,
            )

        updates = []
        payload: dict[str, str] = {}
        if new_start is not None:
            start_dt = _to_datetime(new_start)
            updates.append(("start_time", start_dt.isoformat() if start_dt else None))
            payload["new_start"] = start_dt.isoformat() if start_dt else None
        if new_end is not None:
            end_dt = _to_datetime(new_end)
            updates.append(("end_time", end_dt.isoformat() if end_dt else None))
            payload["new_end"] = end_dt.isoformat() if end_dt else None

        if updates:
            set_clause = ", ".join(f"{column} = ?" for column, _ in updates)
            values = [value for _, value in updates]
            values.append(_now().isoformat())
            values.append(task_id)
            self.db.update(
                f"UPDATE tasks SET {set_clause}, updated_at = ? WHERE id = ?",
                values,
            )
            task = self.get_task(task_id)
            self._schedule_task_reminders(task)
            self._log("task_shifted", task_id=task_id, payload=payload)
            if rule.re_evaluate_on_shift:
                self._log("task_re_evaluation_prompt", task_id=task_id, payload={"priority": task.priority.value})

        return ActionResult(success=True, message="Task shifted", payload=payload)

    def extend_task(self, task_id: int, *, delta: timedelta) -> ActionResult:
        task = self.get_task(task_id)
        new_end = (task.end_time or task.start_time or _now()) + delta
        result = self.shift_task(task_id, new_end=new_end)
        if result.success:
            self._log("task_extended", task_id=task_id, payload={"delta_minutes": int(delta.total_seconds() // 60)})
        return result

    def start_task(self, task_id: int, *, timestamp: datetime | None = None) -> ActionResult:
        task = self.get_task(task_id)
        now = timestamp or _now()
        self.db.update(
            """
            UPDATE tasks
            SET status = ?, active_session_started_at = ?, actual_start = COALESCE(actual_start, ?), updated_at = ?
            WHERE id = ?
            """,
            (
                TaskStatus.IN_PROGRESS.value,
                now.isoformat(),
                now.isoformat(),
                now.isoformat(),
                task_id,
            ),
        )
        self._log("task_started", task_id=task_id, payload={"timestamp": now.isoformat()})
        return ActionResult(success=True, message="Task started")

    def finish_task(self, task_id: int, *, timestamp: datetime | None = None) -> ActionResult:
        task = self.get_task(task_id)
        recorded_at = _now()
        completed_at = timestamp or recorded_at
        active_start = task.active_session_started_at
        duration_minutes = None
        if active_start:
            delta = completed_at - active_start
            minutes = int(round(delta.total_seconds() / 60))
            duration_minutes = minutes if minutes >= 0 else None
        self.db.update(
            """
            UPDATE tasks
            SET status = ?, completed_at = ?, active_session_started_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                TaskStatus.COMPLETED.value,
                completed_at.isoformat(),
                recorded_at.isoformat(),
                task_id,
            ),
        )
        self._log(
            "task_finished",
            task_id=task_id,
            payload={"timestamp": completed_at.isoformat(), "duration_minutes": duration_minutes},
        )
        if duration_minutes and duration_minutes >= 240:
            self._log(
                "task_overwork_detected",
                task_id=task_id,
                payload={"duration_minutes": duration_minutes},
            )
        return ActionResult(success=True, message="Task completed")

    def cancel_task(
        self,
        task_id: int,
        *,
        confirmation_level: int = 0,
        reason: str | None = None,
    ) -> ActionResult:
        task = self.get_task(task_id)
        rule = PRIORITY_RULES[task.priority]
        required = rule.confirmation_level_delete
        if confirmation_level < required:
            self._log(
                "cancel_confirmation_required",
                task_id=task_id,
                payload={"required_level": required, "provided": confirmation_level},
            )
            return ActionResult(
                success=False,
                message="Confirmation required before cancelling task",
                requires_confirmation=True,
                required_level=required,
            )
        now = _now()
        self.db.update(
            """
            UPDATE tasks
            SET status = ?, cancelled_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                TaskStatus.CANCELLED.value,
                now.isoformat(),
                now.isoformat(),
                task_id,
            ),
        )
        payload = {"reason": reason}
        self._log("task_cancelled", task_id=task_id, payload=payload)
        if rule.escalate_logs_on_delete:
            self._log("critical_task_cancelled", task_id=task_id, payload=payload)
        return ActionResult(success=True, message="Task cancelled", payload=payload)

    def adjust_priority(self, task_id: int, new_priority: PriorityLevel | str) -> ActionResult:
        task = self.get_task(task_id)
        new_priority = _to_enum(new_priority, PriorityLevel)
        now = _now()
        self.db.update(
            "UPDATE tasks SET priority = ?, updated_at = ?, auto_drop_at = NULL WHERE id = ?",
            (new_priority.value, now.isoformat(), task_id),
        )
        updated = self.get_task(task_id)
        self._schedule_auto_drop(updated)
        self._schedule_task_reminders(updated)
        self._log(
            "priority_adjusted",
            task_id=task_id,
            payload={"from": task.priority.value, "to": new_priority.value},
        )
        return ActionResult(success=True, message="Priority adjusted")

    def create_link(self, parent_task_id: int, child_task_id: int, relation: str = "parent_child") -> None:
        now = _now()
        self.db.insert(
            """
            INSERT INTO links(parent_task_id, child_task_id, relation, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (parent_task_id, child_task_id, relation, now.isoformat()),
        )
        self._log(
            "tasks_linked",
            task_id=parent_task_id,
            payload={"child": child_task_id, "relation": relation},
        )

    # ------------------------------------------------------------------
    # Contacts & visibility
    # ------------------------------------------------------------------
    def register_contact(self, name: str, *, trust_level: TrustLevel | str, details: dict | None = None) -> ContactRecord:
        trust_level = _to_enum(trust_level, TrustLevel)
        now = _now()
        contact_id = self.db.insert(
            "INSERT INTO contacts(name, trust_level, details) VALUES (?, ?, ?)",
            (name, trust_level.value, self.db.json_dump(details)),
        )
        self._log("contact_registered", payload={"contact_id": contact_id, "trust_level": trust_level.value})
        rows = self.db.query("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        return ContactRecord.from_row(rows[0])

    def get_contact_visibility(self, contact_id: int, task_id: int) -> dict[str, str | None]:
        contact_row = self.db.query("SELECT * FROM contacts WHERE id = ?", (contact_id,))
        if not contact_row:
            raise KeyError(f"Contact {contact_id} not found")
        contact = ContactRecord.from_row(contact_row[0])
        task = self.get_task(task_id)
        visibility: dict[str, str | None] = {"status": None, "type": None, "details": None}
        if contact.trust_level == TrustLevel.U1:
            return visibility
        visibility["status"] = task.status.value
        if contact.trust_level == TrustLevel.U2:
            return visibility
        visibility["type"] = task.task_type.value
        if contact.trust_level == TrustLevel.U3:
            return visibility
        visibility["details"] = task.description
        return visibility

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def set_state(self, state: AgentState | str, *, task_id: int | None = None, note: str | None = None) -> None:
        new_state = _to_enum(state, AgentState)
        now = _now()
        if self._state_row_id is not None:
            self.db.update("UPDATE states SET ended_at = ? WHERE id = ?", (now.isoformat(), self._state_row_id))
            if self.current_state == AgentState.GAMING and self._state_started_at:
                duration = now - self._state_started_at
                if duration >= timedelta(hours=4):
                    self._log(
                        "gaming_overwork_detected",
                        payload={"duration_minutes": int(duration.total_seconds() // 60)},
                    )
        state_id = self.db.insert(
            "INSERT INTO states(state, task_id, started_at, note) VALUES (?, ?, ?, ?)",
            (new_state.value, task_id, now.isoformat(), note),
        )
        self._state_row_id = state_id
        self._state_started_at = now
        self.current_state = new_state
        self._log(
            "state_changed",
            task_id=task_id,
            state=new_state.value,
            payload={"note": note},
        )

    # ------------------------------------------------------------------
    # Triggers & wellbeing
    # ------------------------------------------------------------------
    def run_morning_trigger(self, *, timestamp: datetime | None = None, health_input: str | None = None) -> Digest:
        now = timestamp or _now()
        top_tasks = self._select_top_tasks(limit=3)
        p1_tasks = [task.to_dict() for task in self.list_tasks(include_closed=False) if task.priority == PriorityLevel.P1]
        due_health = False
        if not self.last_health_check or (now - self.last_health_check) >= timedelta(days=2):
            due_health = True
            if health_input:
                self.last_health_check = now
                self._log("health_check_recorded", payload={"input": health_input})
        plan = {
            "top_tasks": [task.to_dict() for task in top_tasks],
            "p1_review": p1_tasks,
            "health_check_due": due_health,
        }
        self._schedule_reply_bank_refresh(now)
        self._log("morning_trigger", payload=plan)
        summary = {
            "top_count": len(top_tasks),
            "p1_count": len(p1_tasks),
        }
        recommendations = []
        if p1_tasks:
            recommendations.append("Promote or drop stale P1 items during review")
        if due_health and not health_input:
            recommendations.append("Collect 3-word health input today")
        return Digest(timestamp=now, summary=summary, recommendations=recommendations)

    def run_night_trigger(
        self,
        *,
        timestamp: datetime | None = None,
        emotion_score: int,
        answers: Sequence[str] | None = None,
    ) -> Digest:
        now = timestamp or _now()
        capacity = self._map_emotion_to_capacity(emotion_score)
        self.capacity = capacity
        self.last_emotion_check = now
        payload = {
            "score": emotion_score,
            "answers": list(answers or []),
            "capacity": capacity,
        }
        self._log("emotion_check_recorded", payload=payload)
        decision = self._apply_capacity_rules(capacity)
        digest = self.generate_daily_digest(now.date())
        digest.recommendations.extend(self._capacity_recommendations(decision))
        self._schedule_reply_bank_refresh(now)
        self._log("night_trigger", payload={"decision": asdict(decision), "digest": digest.summary})
        return digest

    # ------------------------------------------------------------------
    # Events & reminders
    # ------------------------------------------------------------------
    def get_pending_events(self, *, before: datetime | None = None) -> list[EventRecord]:
        before_clause = ""
        params: list = ["pending"]
        if before:
            before_clause = " AND scheduled_for <= ?"
            params.append(before.isoformat())
        rows = self.db.query(
            "SELECT * FROM events WHERE status = ?" + before_clause + " ORDER BY scheduled_for",
            params,
        )
        return [EventRecord.from_row(row) for row in rows]

    def mark_event_completed(self, event_id: int) -> None:
        self.db.update(
            "UPDATE events SET status = 'done' WHERE id = ?",
            (event_id,),
        )

    def refresh_reply_bank(
        self,
        *,
        trust_level: TrustLevel | str,
        intent: str,
        state: AgentState | str,
        variants: Sequence[str],
        generated_at: datetime | None = None,
    ) -> None:
        trust_level = _to_enum(trust_level, TrustLevel)
        state = _to_enum(state, AgentState)
        generated_at = generated_at or _now()
        if len(variants) < 6 or len(variants) > 12:
            raise ValueError("Reply banks must contain between 6 and 12 variants")
        self.db.execute(
            "DELETE FROM reply_bank_entries WHERE trust_level = ? AND intent = ? AND state = ?",
            (trust_level.value, intent, state.value),
        )
        self.db.executemany(
            """
            INSERT INTO reply_bank_entries(trust_level, intent, state, variant_index, content, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (trust_level.value, intent, state.value, index, text, generated_at.isoformat())
                for index, text in enumerate(variants, start=1)
            ),
        )
        self._log(
            "reply_bank_refreshed",
            payload={
                "trust_level": trust_level.value,
                "intent": intent,
                "state": state.value,
                "variant_count": len(variants),
            },
        )

    def get_reply_bank(self, *, trust_level: TrustLevel | str, intent: str, state: AgentState | str) -> list[str]:
        trust_level = _to_enum(trust_level, TrustLevel)
        state = _to_enum(state, AgentState)
        rows = self.db.query(
            """
            SELECT content FROM reply_bank_entries
            WHERE trust_level = ? AND intent = ? AND state = ?
            ORDER BY variant_index
            """,
            (trust_level.value, intent, state.value),
        )
        return [row["content"] for row in rows]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    def generate_daily_digest(self, day: date) -> Digest:
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        completed = self.db.query(
            """
            SELECT * FROM tasks
            WHERE status = 'completed' AND updated_at >= ? AND updated_at < ?
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )
        completed_tasks = [TaskRecord.from_row(row) for row in completed]
        on_time = 0
        for task in completed_tasks:
            reference = task.hard_deadline or task.end_time
            if not reference or (task.completed_at and task.completed_at <= reference):
                on_time += 1
        on_time_ratio = (on_time / len(completed_tasks)) if completed_tasks else 1.0

        overdue = self.db.query(
            """
            SELECT * FROM tasks
            WHERE status NOT IN ('completed','cancelled','dropped')
              AND end_time IS NOT NULL AND end_time < ?
            """,
            (day_end.isoformat(),),
        )
        overdue_tasks = [TaskRecord.from_row(row) for row in overdue]

        session_logs = self.db.query(
            """
            SELECT * FROM logs WHERE action = 'task_finished' AND timestamp >= ? AND timestamp < ?
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )
        durations = [row["payload"] for row in session_logs if row["payload"]]
        longest_session = 0
        for payload in durations:
            import json

            data = json.loads(payload) if isinstance(payload, str) else payload
            longest_session = max(longest_session, data.get("duration_minutes") or 0)

        summary = {
            "completed": len(completed_tasks),
            "on_time_ratio": round(on_time_ratio, 2),
            "spillovers": len(overdue_tasks),
            "longest_session_minutes": longest_session,
        }

        recommendations: list[str] = []
        if on_time_ratio < 0.8:
            recommendations.append("Review scheduling buffers to improve on-time delivery")
        if overdue_tasks:
            recommendations.append("Move overdue low-priority tasks forward or drop them")
        if longest_session >= 240:
            recommendations.append("Plan deliberate pauses to avoid overwork streaks")

        return Digest(timestamp=day_end, summary=summary, recommendations=recommendations)

    def generate_weekly_digest(self, week_start: date) -> Digest:
        period_start = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
        period_end = period_start + timedelta(days=7)
        rows = self.db.query(
            """
            SELECT * FROM tasks
            WHERE updated_at >= ? AND updated_at < ?
            """,
            (period_start.isoformat(), period_end.isoformat()),
        )
        tasks = [TaskRecord.from_row(row) for row in rows]
        closed_critical = [task for task in tasks if task.priority in {PriorityLevel.P3, PriorityLevel.P4} and task.status == TaskStatus.COMPLETED]
        failed_optional = [task for task in tasks if task.priority == PriorityLevel.P2 and task.status in {TaskStatus.CANCELLED, TaskStatus.DROPPED}]

        overwork_logs = self.db.query(
            """
            SELECT * FROM logs
            WHERE action IN ('task_overwork_detected','gaming_overwork_detected')
              AND timestamp >= ? AND timestamp < ?
            """,
            (period_start.isoformat(), period_end.isoformat()),
        )
        overwork_counts = Counter(row["action"] for row in overwork_logs)

        health_logs = self.db.query(
            """
            SELECT * FROM logs WHERE action = 'emotion_check_recorded' AND timestamp >= ? AND timestamp < ?
            """,
            (period_start.isoformat(), period_end.isoformat()),
        )
        scores: list[float] = []
        for row in health_logs:
            import json

            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
            if payload:
                scores.append(payload.get("score", 0))
        trend = sum(scores) / len(scores) if scores else 0

        summary = {
            "closed_p3_p4": len(closed_critical),
            "failed_p2": len(failed_optional),
            "overwork_task": overwork_counts.get("task_overwork_detected", 0),
            "overwork_gaming": overwork_counts.get("gaming_overwork_detected", 0),
            "health_score_avg": round(trend, 2) if trend else 0,
        }
        recommendations: list[str] = []
        if summary["overwork_task"]:
            recommendations.append("Introduce strict 4h review checkpoints on deep work")
        if summary["overwork_gaming"]:
            recommendations.append("Set gaming cooldown reminders after long sessions")
        if scores and trend < 6:
            recommendations.append("Plan lighter loads based on health trend")
        return Digest(timestamp=period_end, summary=summary, recommendations=recommendations)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _schedule_task_reminders(self, task: TaskRecord) -> None:
        self.db.execute("DELETE FROM events WHERE task_id = ? AND event_type = 'reminder'", (task.id,))
        if not task.start_time:
            return
        rule = PRIORITY_RULES[task.priority]
        offsets = sorted({int(offset.total_seconds() // 60) for offset in rule.reminder_offsets})
        for minutes in offsets:
            scheduled_for = task.start_time + timedelta(minutes=minutes)
            if scheduled_for < _now() - timedelta(days=1):
                continue
            self._create_event(
                task.id,
                "reminder",
                scheduled_for,
                {"offset_minutes": minutes, "priority": task.priority.value},
            )

    def _schedule_auto_drop(self, task: TaskRecord) -> None:
        self.db.execute("DELETE FROM events WHERE task_id = ? AND event_type = 'auto_drop'", (task.id,))
        rule = PRIORITY_RULES[task.priority]
        if not rule.auto_drop_after:
            return
        drop_time = task.created_at + rule.auto_drop_after
        self._create_event(
            task.id,
            "auto_drop",
            drop_time,
            {"priority": task.priority.value},
        )
        self.db.update(
            "UPDATE tasks SET auto_drop_at = ? WHERE id = ?",
            (drop_time.isoformat(), task.id),
        )

    def _create_event(self, task_id: int | None, event_type: str, when: datetime, payload: dict | None) -> None:
        self.db.insert(
            """
            INSERT INTO events(task_id, event_type, scheduled_for, status, payload, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (
                task_id,
                event_type,
                when.isoformat(),
                self.db.json_dump(payload),
                _now().isoformat(),
            ),
        )

    def _log(
        self,
        action: str,
        *,
        task_id: int | None = None,
        payload: dict | None = None,
        contact_id: int | None = None,
        state: str | None = None,
    ) -> None:
        self.db.insert(
            """
            INSERT INTO logs(timestamp, action, task_id, contact_id, state, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _now().isoformat(),
                action,
                task_id,
                contact_id,
                state,
                self.db.json_dump(payload),
            ),
        )

    def _select_top_tasks(self, *, limit: int) -> list[TaskRecord]:
        tasks = [task for task in self.list_tasks(include_closed=False)]
        priority_order = {
            PriorityLevel.P4: 0,
            PriorityLevel.P3: 1,
            PriorityLevel.P2: 2,
            PriorityLevel.P1: 3,
        }
        fallback = datetime.max.replace(tzinfo=timezone.utc)
        tasks.sort(key=lambda task: (priority_order[task.priority], task.start_time or fallback))
        return tasks[:limit]

    def _schedule_reply_bank_refresh(self, timestamp: datetime) -> None:
        self._create_event(None, "reply_bank_refresh", timestamp, None)

    def _map_emotion_to_capacity(self, score: int) -> float:
        if score < 3:
            return 0.0
        if score < 5:
            return 0.45
        if score < 7:
            return 0.75
        return 1.0

    def _apply_capacity_rules(self, capacity: float) -> CapacityDecision:
        tasks = [task for task in self.list_tasks(include_closed=False)]
        suggested: list[int] = []
        required: list[int] = []
        force_rest = capacity == 0.0
        if capacity < 0.75:
            suggested = [task.id for task in tasks if task.priority in {PriorityLevel.P1, PriorityLevel.P2}]
        if capacity < 0.45:
            required = [task.id for task in tasks if task.priority in {PriorityLevel.P2, PriorityLevel.P3}]
        if force_rest:
            self.set_state(AgentState.SLEEP, note="Capacity check enforced rest")
        if suggested:
            for task_id in suggested:
                self._log("capacity_suggest_drop", task_id=task_id, payload={"capacity": capacity})
        if required:
            for task_id in required:
                self._log("capacity_require_drop", task_id=task_id, payload={"capacity": capacity})
        return CapacityDecision(capacity=capacity, suggested_drops=suggested, required_drops=required, force_rest=force_rest)

    def _capacity_recommendations(self, decision: CapacityDecision) -> list[str]:
        recommendations: list[str] = []
        if decision.force_rest:
            recommendations.append("Capacity critically low – rest scheduled")
        if decision.required_drops:
            recommendations.append("Drop or reschedule all P3/P2 items before accepting new work")
        elif decision.suggested_drops:
            recommendations.append("Consider dropping optional tasks to match reduced capacity")
        return recommendations


__all__ = ["ManagementService", "CapacityDecision"]
from datetime import datetime, timedelta, timezone

import pytest

from management import AgentState, ManagementService, PriorityLevel, TaskStatus, TaskType, TrustLevel


@pytest.fixture()
def service() -> ManagementService:
    return ManagementService()


def _count_events(service: ManagementService, event_type: str) -> int:
    rows = service.db.query("SELECT COUNT(*) AS c FROM events WHERE event_type = ?", (event_type,))
    return rows[0]["c"]


def _fetch_logs(service: ManagementService, action: str) -> list[dict]:
    rows = service.db.query("SELECT payload FROM logs WHERE action = ?", (action,))
    results: list[dict] = []
    for row in rows:
        payload = row["payload"]
        if payload:
            import json

            results.append(json.loads(payload) if isinstance(payload, str) else payload)
        else:
            results.append({})
    return results


def test_create_task_schedules_reminders_and_auto_drop(service: ManagementService) -> None:
    start_time = datetime.now(timezone.utc) + timedelta(days=1)
    task = service.create_task(
        "Draft strategy",
        task_type=TaskType.WORK,
        priority=PriorityLevel.P1,
        start_time=start_time,
    )
    reminder_events = service.db.query(
        "SELECT event_type, scheduled_for, payload FROM events WHERE task_id = ? ORDER BY scheduled_for",
        (task.id,),
    )
    assert {row["event_type"] for row in reminder_events} == {"reminder", "auto_drop"}
    reminder_offsets = [
        (datetime.fromisoformat(row["scheduled_for"]) - task.start_time).total_seconds() // 60
        for row in reminder_events
        if row["event_type"] == "reminder"
    ]
    assert sorted(reminder_offsets) == [-240, -30, 0]
    auto_drop = [row for row in reminder_events if row["event_type"] == "auto_drop"][0]
    drop_time = datetime.fromisoformat(auto_drop["scheduled_for"])
    assert pytest.approx((drop_time - task.created_at).total_seconds(), abs=5) == 7 * 24 * 3600


def test_shift_task_requires_confirmation_for_p3(service: ManagementService) -> None:
    start_time = datetime.now(timezone.utc) + timedelta(hours=2)
    task = service.create_task("Write report", priority=PriorityLevel.P3, start_time=start_time)
    result = service.shift_task(task.id, new_start=start_time + timedelta(hours=1))
    assert not result.success and result.requires_confirmation and result.required_level == 1
    confirmed = service.shift_task(
        task.id,
        new_start=start_time + timedelta(hours=1),
        confirmation_level=1,
    )
    assert confirmed.success
    re_eval_logs = _fetch_logs(service, "task_re_evaluation_prompt")
    assert re_eval_logs and re_eval_logs[-1]["priority"] == PriorityLevel.P3.value


def test_cancel_task_requires_double_confirm_for_p4(service: ManagementService) -> None:
    task = service.create_task("Ship hotfix", priority=PriorityLevel.P4)
    first = service.cancel_task(task.id, confirmation_level=1)
    assert not first.success and first.required_level == 2
    second = service.cancel_task(task.id, confirmation_level=2, reason="Replaced by new build")
    assert second.success
    critical_logs = _fetch_logs(service, "critical_task_cancelled")
    assert critical_logs and critical_logs[-1]["reason"] == "Replaced by new build"


def test_morning_trigger_prepares_plan(service: ManagementService) -> None:
    now = datetime.now(timezone.utc)
    service.create_task("Critical deploy", priority=PriorityLevel.P4, start_time=now + timedelta(hours=1))
    service.create_task("Refine backlog", priority=PriorityLevel.P2, start_time=now + timedelta(hours=2))
    service.create_task("Personal errands", priority=PriorityLevel.P1, start_time=now + timedelta(hours=3))
    digest = service.run_morning_trigger(timestamp=now)
    assert digest.summary["top_count"] <= 3
    assert _count_events(service, "reply_bank_refresh") >= 1
    if digest.summary["p1_count"]:
        assert any("P1" in rec or "Promote" in rec for rec in digest.recommendations)


def test_night_trigger_capacity_rules_force_rest(service: ManagementService) -> None:
    service.create_task("Optional idea", priority=PriorityLevel.P1)
    service.create_task("Backlog grooming", priority=PriorityLevel.P2)
    service.create_task("Finish module", priority=PriorityLevel.P3)
    digest = service.run_night_trigger(emotion_score=2, answers=["tired", "stressed"])
    assert service.current_state == AgentState.SLEEP
    suggest_logs = _fetch_logs(service, "capacity_require_drop")
    affected_tasks = {log.get("capacity") for log in suggest_logs}
    assert 0.0 in affected_tasks
    assert any("Drop" in rec for rec in digest.recommendations)


def test_overwork_detection_on_task_finish(service: ManagementService) -> None:
    task = service.create_task("Deep work", priority=PriorityLevel.P3)
    start_time = datetime.now(timezone.utc) - timedelta(hours=5)
    # emulate starting earlier
    service.db.update(
        "UPDATE tasks SET active_session_started_at = ?, status = ? WHERE id = ?",
        (start_time.isoformat(), TaskStatus.IN_PROGRESS.value, task.id),
    )
    result = service.finish_task(task.id)
    assert result.success
    logs = _fetch_logs(service, "task_overwork_detected")
    assert logs and logs[-1]["duration_minutes"] >= 300


def test_generate_digests_cover_core_metrics(service: ManagementService) -> None:
    today = datetime.now(timezone.utc)
    completed_task = service.create_task(
        "Complete doc",
        priority=PriorityLevel.P3,
        start_time=today - timedelta(hours=2),
        end_time=today - timedelta(hours=1),
    )
    service.finish_task(completed_task.id, timestamp=today - timedelta(hours=1))
    cancelled = service.create_task("Skip chores", priority=PriorityLevel.P2)
    service.cancel_task(cancelled.id, confirmation_level=0)
    daily = service.generate_daily_digest(today.date())
    assert "completed" in daily.summary and daily.summary["completed"] >= 1
    weekly = service.generate_weekly_digest(today.date())
    assert weekly.summary["closed_p3_p4"] >= 1
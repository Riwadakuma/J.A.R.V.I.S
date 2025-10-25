from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Dict, Mapping

try:  # pragma: no cover - runtime import guard for script execution
    from core.executor.management import ManagementExecutor, TaskExecutionResult
except ModuleNotFoundError:  # pragma: no cover - allow running directly from tool package
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from core.executor.management import ManagementExecutor, TaskExecutionResult  # type: ignore

from toolrunner.management.service import ManagementService


_EXECUTOR_LOCK = threading.RLock()
_EXECUTOR: ManagementExecutor | None = None
_EXECUTOR_KEY: tuple[str | None, tuple[tuple[str, int], ...]] | None = None
_BASE_DIR = Path(__file__).resolve().parents[1]


def _resolve_db_path(raw: str | None) -> str | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (_BASE_DIR / raw).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _normalise_limits(limits: Mapping[str, Any] | None) -> dict[str, int]:
    result: dict[str, int] = {}
    if not limits:
        return result
    for key, value in limits.items():
        try:
            result[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"E_INVALID_LIMIT:{key}") from exc
    return result


def _config_signature(config: Mapping[str, Any]) -> tuple[str | None, tuple[tuple[str, int], ...]]:
    mgmt = dict((config.get("management") or {})) if isinstance(config, Mapping) else {}
    db_path = mgmt.get("db_path")
    limits = _normalise_limits(mgmt.get("per_type_limits"))
    key = _resolve_db_path(db_path) if db_path else None
    ordered_limits = tuple(sorted(limits.items()))
    return key, ordered_limits


def _get_executor(config: Mapping[str, Any]) -> ManagementExecutor:
    global _EXECUTOR, _EXECUTOR_KEY
    with _EXECUTOR_LOCK:
        signature = _config_signature(config)
        if _EXECUTOR is not None and _EXECUTOR_KEY == signature:
            return _EXECUTOR

        db_path = signature[0]
        limits_map = dict(signature[1])
        service = ManagementService(db_path=db_path)
        _EXECUTOR = ManagementExecutor(service=service, per_type_limits=limits_map)
        _EXECUTOR_KEY = signature
        return _EXECUTOR


def _build_task_payload(args: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, Mapping):
        raise ValueError("E_INVALID_ARGS")

    payload = dict(args)
    if "action" not in payload:
        raise ValueError("E_ARG_MISSING:action")

    task_args = dict(payload.pop("args", {}) or {})
    known = {"action", "task_type", "trace_id", "correlation_id", "action_id"}
    for key in list(payload.keys()):
        if key in known:
            continue
        task_args[key] = payload.pop(key)

    envelope: Dict[str, Any] = {"action": payload["action"], "args": task_args}
    if "task_type" in payload:
        envelope["task_type"] = payload["task_type"]
    if payload.get("trace_id"):
        envelope["trace_id"] = payload["trace_id"]
    if payload.get("correlation_id"):
        envelope["correlation_id"] = payload["correlation_id"]
    if payload.get("action_id"):
        envelope["action_id"] = payload["action_id"]
    return envelope


def cmd_management_execute(args: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    executor = _get_executor(config)
    envelope = _build_task_payload(args)
    with _EXECUTOR_LOCK:
        result: TaskExecutionResult = executor.execute(envelope)
    return result.model_dump(by_alias=True)


__all__ = ["cmd_management_execute"]
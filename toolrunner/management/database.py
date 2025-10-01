
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


def _serialize(value: Any) -> Any:
    """Serialize dataclasses and dictionaries into JSON."""

    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if is_dataclass(value):
        return json.dumps(asdict(value), ensure_ascii=False)
    return value


class ManagementDatabase:
    """Thin wrapper above sqlite that provides schema management."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON;")
        self._initialise_schema()

    def close(self) -> None:
        """Close the underlying connection."""

        with self._lock:
            self._conn.close()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        """Yield a cursor and commit on success."""

        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    def execute(self, query: str, parameters: Iterable[Any] | None = None) -> sqlite3.Cursor:
        """Execute a query and return the cursor."""

        with self.cursor() as cur:
            cur.execute(query, tuple(parameters or ()))
            return cur

    def executemany(self, query: str, seq_of_parameters: Iterable[Iterable[Any]]) -> None:
        """Execute the same statement for a sequence of parameters."""

        with self.cursor() as cur:
            cur.executemany(query, [tuple(params) for params in seq_of_parameters])

    def query(self, query: str, parameters: Iterable[Any] | None = None) -> list[sqlite3.Row]:
        """Execute a select statement and return rows."""

        with self.cursor() as cur:
            cur.execute(query, tuple(parameters or ()))
            return cur.fetchall()

    def _initialise_schema(self) -> None:
        """Create tables if this is the first run."""

        with self.cursor() as cur:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    hard_deadline TEXT,
                    soft_deadline TEXT,
                    default_reminder_offset INTEGER NOT NULL DEFAULT 30,
                    auto_drop_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    cancelled_at TEXT,
                    active_session_started_at TEXT,
                    actual_start TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    event_type TEXT NOT NULL,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    task_id INTEGER,
                    contact_id INTEGER,
                    state TEXT,
                    payload TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state TEXT NOT NULL,
                    task_id INTEGER,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    capacity REAL,
                    note TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    details TEXT
                );

                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_task_id INTEGER NOT NULL,
                    child_task_id INTEGER NOT NULL,
                    relation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (child_task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reply_bank_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trust_level TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    state TEXT NOT NULL,
                    variant_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    UNIQUE(trust_level, intent, state, variant_index)
                );
                """
            )

    def insert(self, query: str, parameters: Iterable[Any]) -> int:
        """Execute an insert and return the last row id."""

        with self.cursor() as cur:
            cur.execute(query, tuple(parameters))
            return int(cur.lastrowid)

    def update(self, query: str, parameters: Iterable[Any]) -> None:
        """Execute an update statement."""

        self.execute(query, parameters)

    @staticmethod
    def json_dump(value: Any) -> str | None:
        """Serialise value into JSON if required."""

        return _serialize(value)
"""SQLite 연결, 스키마, KST 시간 유틸."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def db_path() -> str:
    return os.environ.get("PAWCARE_DB") or str(ROOT / "pawcare.db")


def now_iso() -> str:
    return datetime.now(KST).replace(microsecond=0, tzinfo=None).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """FastAPI 의존성: 요청당 연결 1개, 정상 종료 시 commit."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    breed TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    avatar_color TEXT NOT NULL DEFAULT '#A5AE98',
    owner_name TEXT NOT NULL,
    care_context TEXT NOT NULL DEFAULT '{}',
    attending INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS care_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    dog_id INTEGER NOT NULL REFERENCES dogs(id),
    author_id INTEGER NOT NULL REFERENCES staff(id),
    record_type TEXT NOT NULL,
    structured_value TEXT,
    content TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    parent_status TEXT NOT NULL DEFAULT 'private',
    parent_text TEXT,
    parent_approved_by INTEGER REFERENCES staff(id),
    parent_approved_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    dog_id INTEGER NOT NULL REFERENCES dogs(id),
    source_record_id INTEGER REFERENCES care_records(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'normal',
    created_by INTEGER NOT NULL REFERENCES staff(id),
    assignee_id INTEGER REFERENCES staff(id),
    acknowledgment_status TEXT NOT NULL DEFAULT 'pending',
    acknowledged_by INTEGER REFERENCES staff(id),
    acknowledged_at TEXT,
    action_status TEXT NOT NULL DEFAULT 'todo',
    completion_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    ai_suggested INTEGER NOT NULL DEFAULT 0,
    CHECK (acknowledgment_status IN ('pending','acknowledged')),
    CHECK (action_status IN ('todo','in_progress','completed'))
);
CREATE TABLE IF NOT EXISTS task_action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    actor_id INTEGER NOT NULL REFERENCES staff(id),
    action_type TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_org ON tasks(org_id, action_status);
CREATE INDEX IF NOT EXISTS idx_records_dog ON care_records(dog_id, observed_at);
"""

TABLES = ["task_action_logs", "tasks", "care_records", "dogs", "staff", "organizations"]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def row(r):
    return dict(r) if r is not None else None

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
    conn = sqlite3.connect(db_path(), check_same_thread=False)  # 요청 1개 = 연결 1개(순차 사용)
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
CREATE TABLE IF NOT EXISTS routine_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    record_type TEXT,
    handoff_label TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
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
    attending INTEGER NOT NULL DEFAULT 1,
    photo TEXT
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
    parent_approved_at TEXT,
    block_id INTEGER REFERENCES routine_blocks(id)
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
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('staff','parent')),
    staff_id INTEGER REFERENCES staff(id),
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guardian_dogs (
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    dog_id INTEGER NOT NULL REFERENCES dogs(id),
    PRIMARY KEY (account_id, dog_id)
);
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT NOT NULL UNIQUE,
    org_id INTEGER NOT NULL REFERENCES organizations(id),
    dog_id INTEGER NOT NULL REFERENCES dogs(id),
    created_by INTEGER NOT NULL REFERENCES staff(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    used_by INTEGER REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts ON login_attempts(key, at);
CREATE INDEX IF NOT EXISTS idx_tasks_org ON tasks(org_id, action_status);
CREATE INDEX IF NOT EXISTS idx_records_dog ON care_records(dog_id, observed_at);
"""

TABLES = ["sessions", "login_attempts", "invites", "guardian_dogs", "accounts", "task_action_logs", "tasks",
          "care_records", "routine_blocks", "dogs", "staff", "organizations"]


SAMPLE_PHOTOS = {"보리": "bori", "두부": "tofu", "모카": "mocha", "밤이": "bami", "콩이": "kongi", "구름": "cloud"}


# 공통 일과 템플릿(일반적인 이름). (이름, 시작, 끝, 설명, 기본 기록 유형, 인계 표시)
ROUTINE_TEMPLATE = [
    ("등원·컨디션 체크", "08:00", "10:00", "도착한 아이의 컨디션과 보호자 전달사항을 확인합니다.", "특이사항", None),
    ("오전 교육·놀이", "10:00", "12:00", "오전 프로그램을 진행하고 활동을 기록합니다.", "활동", None),
    ("점심·휴식", "12:00", "13:00", "식사량과 배변 상태를 기록하고 휴식을 돕습니다.", "식사", None),
    ("오후 산책·놀이", "13:00", "16:00", "오후 담당자가 이어받아 산책과 놀이를 진행합니다.", "활동", "오전 → 오후 담당자"),
    ("그루밍·정리", "16:00", "17:00", "그루밍과 하원 전 정리를 합니다.", "기타", None),
    ("하원 준비", "17:00", "20:00", "보호자 전달 내용을 정리하고 하원을 돕습니다.", "기타", None),
]


def block_for(blocks: list, observed_at: str):
    """기록 시각(YYYY-MM-DDTHH:MM…)이 속한 일과 구간 id. 영업시간 밖이면 None."""
    t = observed_at[11:16]
    for b in blocks:
        if b["start_time"] <= t < b["end_time"]:
            return b["id"]
    return None


def ensure_routine(conn: sqlite3.Connection) -> None:
    """일과 템플릿이 없는 유치원에 채우고, 구간이 비어 있는 기록에 구간을 연결한다(멱등)."""
    for org in conn.execute("SELECT id FROM organizations").fetchall():
        if conn.execute("SELECT 1 FROM routine_blocks WHERE org_id=?", (org["id"],)).fetchone() is None:
            conn.executemany(
                "INSERT INTO routine_blocks(org_id,name,start_time,end_time,description,record_type,handoff_label,sort_order)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(org["id"], *t, i) for i, t in enumerate(ROUTINE_TEMPLATE)])
        blocks = conn.execute("SELECT * FROM routine_blocks WHERE org_id=? ORDER BY sort_order", (org["id"],)).fetchall()
        for r in conn.execute("SELECT id, observed_at FROM care_records WHERE org_id=? AND block_id IS NULL", (org["id"],)).fetchall():
            bid = block_for(blocks, r["observed_at"])
            if bid:
                conn.execute("UPDATE care_records SET block_id=? WHERE id=?", (bid, r["id"]))


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if "block_id" not in {r["name"] for r in conn.execute("PRAGMA table_info(care_records)")}:
        conn.execute("ALTER TABLE care_records ADD COLUMN block_id INTEGER REFERENCES routine_blocks(id)")
    # 마이그레이션: photo 컬럼이 없는 기존 DB에 추가하고, 샘플 반려견에만 샘플 사진을 연결한다.
    if "photo" not in {r["name"] for r in conn.execute("PRAGMA table_info(dogs)")}:
        conn.execute("ALTER TABLE dogs ADD COLUMN photo TEXT")
        for name, f in SAMPLE_PHOTOS.items():
            conn.execute("UPDATE dogs SET photo=? WHERE name=? AND photo IS NULL", (f"assets/dogs/{f}.webp", name))
    ensure_routine(conn)
    from .seed import seed_accounts   # 이전 버전 DB: 계정이 하나도 없으면 샘플 직원·보호자의 데모 계정을 만든다
    seed_accounts(conn)
    conn.commit()


def upload_dir() -> Path:
    """사용자가 올린 사진 저장 위치(Git 제외). 테스트·배포에서 PAWCARE_UPLOADS로 바꿀 수 있다."""
    return Path(os.environ.get("PAWCARE_UPLOADS") or ROOT / "uploads")


def row(r):
    return dict(r) if r is not None else None

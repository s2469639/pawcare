"""하루 일과 구간: 구간별 기록 현황과 인계 시점 요약."""
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..database import KST, get_db
from ..deps import current_staff
from .common import TASK_SELECT, task_dict, today_prefix

router = APIRouter(prefix="/api/routine", tags=["routine"])

# 요일별 프로그램(예시 템플릿, 편집 기능 없음)
PROGRAMS = {
    0: ("사회화", "다른 아이·사람과 편안하게 어울리기"),
    1: ("감각 놀이", "냄새·소리·촉감 자극에 익숙해지기"),
    2: ("지능 개발", "노즈워크와 퍼즐 놀이"),
    3: ("운동", "산책과 장애물 놀이"),
    4: ("예절 교육", "기다려·앉아 등 기본 예절 연습"),
}


def _blocks(db, org_id):
    return [dict(b) for b in db.execute("SELECT * FROM routine_blocks WHERE org_id=? ORDER BY sort_order", (org_id,))]


@router.get("")
def routine(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org, today = staff["org_id"], today_prefix() + "%"
    now = datetime.now(KST)
    hhmm = now.strftime("%H:%M")
    blocks = _blocks(db, org)
    total = db.execute("SELECT COUNT(*) FROM dogs WHERE org_id=? AND attending=1", (org,)).fetchone()[0]
    for b in blocks:
        r = db.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT dog_id) AS dogs, MAX(observed_at) AS last FROM care_records "
                       "WHERE block_id=? AND observed_at LIKE ?", (b["id"], today)).fetchone()
        b.update(record_count=r["n"], dog_count=r["dogs"], last_at=r["last"], dogs_total=total)
    current = next((b["id"] for b in blocks if b["start_time"] <= hhmm < b["end_time"]), None)
    default = current
    if default is None:   # 영업시간 밖: 오늘 가장 최근에 기록이 있는 구간(없으면 첫 구간)을 보여준다
        with_rec = [b for b in blocks if b["last_at"]]
        default = max(with_rec, key=lambda b: b["last_at"])["id"] if with_rec else (blocks[0]["id"] if blocks else None)
    title, detail = PROGRAMS.get(now.weekday(), ("주말", "정규 프로그램 없음"))
    return {"date": now.date().isoformat(), "now_time": hhmm, "open": current is not None,
            "current_block_id": current, "default_block_id": default, "blocks": blocks,
            "program": {"title": title, "detail": detail, "weekday": "월화수목금토일"[now.weekday()]}}


@router.get("/{block_id}")
def block_detail(block_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org, today = staff["org_id"], today_prefix() + "%"
    b = db.execute("SELECT * FROM routine_blocks WHERE id=? AND org_id=?", (block_id, org)).fetchone()
    if b is None:
        raise HTTPException(404, "일과 구간을 찾을 수 없습니다.")
    dogs = []
    for d in db.execute("SELECT id,name,breed,photo,avatar_color FROM dogs WHERE org_id=? AND attending=1 ORDER BY id", (org,)):
        recs = [dict(r) for r in db.execute(
            "SELECT r.id,r.record_type,r.structured_value,r.content,r.observed_at,s.name AS author_name FROM care_records r "
            "JOIN staff s ON s.id=r.author_id WHERE r.dog_id=? AND r.block_id=? AND r.observed_at LIKE ? "
            "ORDER BY r.observed_at DESC, r.id DESC", (d["id"], block_id, today))]
        open_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE dog_id=? AND action_status!='completed'", (d["id"],)).fetchone()[0]
        dogs.append({**dict(d), "records": recs, "open_task_count": open_tasks})
    handoff = None
    if b["handoff_label"]:
        tasks = [task_dict(t) for t in db.execute(
            TASK_SELECT + " WHERE t.org_id=? AND t.action_status!='completed' ORDER BY rank_order, prio_order, t.created_at DESC", (org,))]
        handoff = {"label": b["handoff_label"], "at": b["start_time"], "tasks": tasks,
                   "counts": {"pending": sum(t["acknowledgment_status"] == "pending" for t in tasks),
                              "todo": sum(t["acknowledgment_status"] == "acknowledged" and t["action_status"] == "todo" for t in tasks),
                              "in_progress": sum(t["action_status"] == "in_progress" for t in tasks)}}
    return {"block": dict(b), "dogs": dogs, "with_record": sum(1 for d in dogs if d["records"]), "handoff": handoff}

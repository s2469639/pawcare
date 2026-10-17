"""하루 일과 구간: 구간별 기록 현황과 인계 시점 요약."""
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..database import KST, get_db
from ..deps import current_staff
from .attendance import day_view, present_dog_ids
from .calendar import today_events
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


def _photo_stats(db, org_id: int, block_id: int, today: str) -> dict:
    """이 구간 기록에 오늘 첨부된 사진을 반려견별로 센다: 공개됨(shared) / 공개 전(pending).
    사진에 태그된 아이 기준이며, '공개됨'은 그 아이의 보호자에게 실제로 공개된 사진이다."""
    stats: dict = {}
    for r in db.execute(
            "SELECT md.dog_id, EXISTS (SELECT 1 FROM media_shares s WHERE s.media_id=m.id AND s.dog_id=md.dog_id) AS shared "
            "FROM media m JOIN care_records r ON r.id=m.record_id JOIN media_dogs md ON md.media_id=m.id "
            "WHERE r.block_id=? AND r.org_id=? AND r.observed_at LIKE ?", (block_id, org_id, today)):
        st = stats.setdefault(r["dog_id"], {"shared": 0, "pending": 0})
        st["shared" if r["shared"] else "pending"] += 1
    return stats


def _blocks(db, org_id):
    return [dict(b) for b in db.execute("SELECT * FROM routine_blocks WHERE org_id=? ORDER BY sort_order", (org_id,))]


@router.get("")
def routine(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org, today = staff["org_id"], today_prefix() + "%"
    now = datetime.now(KST)
    hhmm = now.strftime("%H:%M")
    blocks = _blocks(db, org)
    present = present_dog_ids(db, org, today_prefix())          # 구간의 대상은 오늘 등원 체크한(출석) 아이
    total = len(present)
    for b in blocks:
        r = db.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT dog_id) AS dogs, MAX(observed_at) AS last FROM care_records "
                       "WHERE block_id=? AND observed_at LIKE ?", (b["id"], today)).fetchone()
        b.update(record_count=r["n"], dog_count=r["dogs"], last_at=r["last"], dogs_total=total, share_prompt=bool(b["share_prompt"]))
        if b["share_prompt"]:
            b["dogs_shared"] = sum(1 for d, st in _photo_stats(db, org, b["id"], today).items() if d in present and st["shared"])
    current = next((b["id"] for b in blocks if b["start_time"] <= hhmm < b["end_time"]), None)
    default = current
    if default is None:   # 영업시간 밖: 오늘 가장 최근에 기록이 있는 구간(없으면 첫 구간)을 보여준다
        with_rec = [b for b in blocks if b["last_at"]]
        default = max(with_rec, key=lambda b: b["last_at"])["id"] if with_rec else (blocks[0]["id"] if blocks else None)
    kind = db.execute("SELECT kind FROM organizations WHERE id=?", (org,)).fetchone()["kind"]
    # 요일별 예시 프로그램은 유치원 전용이다(호텔은 오늘의 캘린더 일정만 보여준다)
    program = None
    if kind == "daycare":
        title, detail = PROGRAMS.get(now.weekday(), ("주말", "정규 프로그램 없음"))
        program = {"title": title, "detail": detail, "weekday": "월화수목금토일"[now.weekday()]}
    return {"date": now.date().isoformat(), "now_time": hhmm, "open": current is not None,
            "current_block_id": current, "default_block_id": default, "blocks": blocks,
            "today_events": [{k: e[k] for k in ("id", "title", "kind", "start_time", "end_time")} for e in today_events(db, org)],
            "org_kind": kind, "program": program, "dogs_present": total,
            "attendance": day_view(db, org, now.date())["summary"]}


@router.get("/{block_id}")
def block_detail(block_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org, today = staff["org_id"], today_prefix() + "%"
    b = db.execute("SELECT * FROM routine_blocks WHERE id=? AND org_id=?", (block_id, org)).fetchone()
    if b is None:
        raise HTTPException(404, "일과 구간을 찾을 수 없습니다.")
    dogs = []
    stats = _photo_stats(db, org, block_id, today) if b["share_prompt"] else {}
    present = present_dog_ids(db, org, today_prefix())
    for d in db.execute("SELECT id,name,breed,photo,avatar_color FROM dogs WHERE org_id=? AND attending=1 ORDER BY id", (org,)):
        if d["id"] not in present:
            continue
        recs = [dict(r) for r in db.execute(
            "SELECT r.id,r.record_type,r.structured_value,r.content,r.observed_at,s.name AS author_name FROM care_records r "
            "JOIN staff s ON s.id=r.author_id WHERE r.dog_id=? AND r.block_id=? AND r.observed_at LIKE ? "
            "ORDER BY r.observed_at DESC, r.id DESC", (d["id"], block_id, today))]
        open_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE dog_id=? AND action_status!='completed'", (d["id"],)).fetchone()[0]
        dogs.append({**dict(d), "records": recs, "open_task_count": open_tasks, "photos": stats.get(d["id"], {"shared": 0, "pending": 0})})
    handoff = None
    if b["handoff_label"]:
        tasks = [task_dict(t) for t in db.execute(
            TASK_SELECT + " WHERE t.org_id=? AND t.action_status!='completed' ORDER BY rank_order, prio_order, t.created_at DESC", (org,))]
        handoff = {"label": b["handoff_label"], "at": b["start_time"], "tasks": tasks,
                   "counts": {"pending": sum(t["acknowledgment_status"] == "pending" for t in tasks),
                              "todo": sum(t["acknowledgment_status"] == "acknowledged" and t["action_status"] == "todo" for t in tasks),
                              "in_progress": sum(t["action_status"] == "in_progress" for t in tasks)}}
    share = None
    if b["share_prompt"]:     # 사진 공유 시점: 이 구간 사진을 아직 보호자에게 공개하지 않은 아이를 보여준다
        share = {"dogs_total": len(dogs),
                 "dogs_shared": sum(1 for d in dogs if d["photos"]["shared"]),
                 "dogs_pending": sum(1 for d in dogs if not d["photos"]["shared"] and d["photos"]["pending"]),
                 "dogs_none": sum(1 for d in dogs if not d["photos"]["shared"] and not d["photos"]["pending"])}
    return {"block": dict(b) | {"share_prompt": bool(b["share_prompt"])}, "dogs": dogs, "with_record": sum(1 for d in dogs if d["records"]),
            "handoff": handoff, "share": share}

"""직원 목록, 대시보드, 데모 초기화, 보호자 미리보기."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..database import KST, connect, get_db
from ..deps import current_staff
from ..seed import reset
from .common import TASK_SELECT, dog_dict, task_dict, today_prefix
from datetime import datetime

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/demo/staff")
def demo_staff(db: sqlite3.Connection = Depends(get_db)):
    """데모용 직원 선택 목록(로그인 대체). 실서비스에서는 인증으로 교체."""
    return [dict(r) for r in db.execute(
        "SELECT s.id, s.name, s.role, s.org_id, o.name AS org_name FROM staff s "
        "JOIN organizations o ON o.id=s.org_id ORDER BY s.id")]


@router.post("/demo/reset")
def demo_reset():
    conn = connect()
    try:
        reset(conn)
    finally:
        conn.close()
    return {"ok": True}


@router.get("/staff")
def staff_list(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT id,name,role,org_id FROM staff WHERE org_id=? ORDER BY id",
                                        (staff["org_id"],))]


@router.get("/dashboard")
def dashboard(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org = staff["org_id"]
    c = db.execute(
        "SELECT COALESCE(SUM(acknowledgment_status='pending' AND action_status!='completed'),0) AS needs_ack,"
        " COALESCE(SUM(action_status='todo'),0) AS todo,"
        " COALESCE(SUM(action_status='in_progress'),0) AS in_progress,"
        " COALESCE(SUM(action_status='completed'),0) AS completed,"
        " COALESCE(SUM(acknowledgment_status='pending' AND action_status!='completed' AND assignee_id=?),0) AS mine_pending,"
        " COUNT(*) AS total FROM tasks WHERE org_id=?", (staff["id"], org)).fetchone()
    dogs = db.execute("SELECT COUNT(*) FROM dogs WHERE org_id=? AND attending=1", (org,)).fetchone()[0]
    tasks = db.execute(TASK_SELECT + " WHERE t.org_id=? ORDER BY rank_order, prio_order, t.created_at DESC", (org,))
    wd = "월화수목금토일"[datetime.now(KST).weekday()]
    return {"date": today_prefix(), "weekday": wd, "attending_dogs": dogs, "counts": dict(c),
            "tasks": [task_dict(t) for t in tasks]}


@router.get("/parent/dogs")
def parent_dogs(db: sqlite3.Connection = Depends(get_db)):
    """보호자 데모: 샘플 유치원(첫 번째 조직)의 반려견만 노출. 내부 정보는 포함하지 않는다."""
    return [{"id": r["id"], "name": r["name"], "breed": r["breed"], "owner_name": r["owner_name"],
             "avatar_color": r["avatar_color"]}
            for r in db.execute("SELECT * FROM dogs WHERE org_id=(SELECT MIN(id) FROM organizations) ORDER BY id")]


@router.get("/parent/dogs/{dog_id}/preview")
def parent_preview(dog_id: int, db: sqlite3.Connection = Depends(get_db)):
    dog = db.execute("SELECT * FROM dogs WHERE id=? AND org_id=(SELECT MIN(id) FROM organizations)", (dog_id,)).fetchone()
    if dog is None:
        raise HTTPException(404, "반려견을 찾을 수 없습니다.")
    recs = db.execute(
        "SELECT id, record_type, parent_text, parent_approved_at FROM care_records "
        "WHERE dog_id=? AND parent_status='approved' ORDER BY observed_at DESC", (dog_id,))
    d = dog_dict(dog)
    return {"dog": {"id": d["id"], "name": d["name"], "breed": d["breed"], "age_text": d["age_text"],
                    "owner_name": d["owner_name"], "avatar_color": d["avatar_color"]},
            "records": [dict(r) for r in recs]}

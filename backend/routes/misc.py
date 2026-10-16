"""직원 목록, 대시보드, 데모 초기화, 보호자 미리보기."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..database import KST, connect, get_db
from ..deps import current_staff
from .auth import require_demo
from ..seed import reset
from .common import TASK_SELECT, dog_dict, task_dict, today_prefix
from datetime import datetime

router = APIRouter(prefix="/api", tags=["misc"])


@router.post("/demo/reset", dependencies=[Depends(require_demo)])
def demo_reset():
    """데모 모드 전용: 샘플 데이터를 처음 상태로 되돌린다(모든 세션도 함께 초기화됨)."""
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

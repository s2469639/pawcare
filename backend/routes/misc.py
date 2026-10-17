"""직원 목록, 대시보드, 데모 초기화, 보호자 미리보기."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..database import KST, connect, get_db
from ..deps import current_staff
from .auth import require_demo
from ..seed import reset
from .attendance import day_view
from .common import TASK_SELECT, dog_dict, stay_fields, task_dict, today_prefix
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
    att = day_view(db, org, datetime.now(KST).date())["summary"]
    dogs = att["present"]                                  # 오늘 돌봄 중 = 오늘 등원 체크한 아이
    tasks = db.execute(TASK_SELECT + " WHERE t.org_id=? ORDER BY rank_order, prio_order, t.created_at DESC", (org,))
    wd = "월화수목금토일"[datetime.now(KST).weekday()]
    stay = None
    if db.execute("SELECT kind FROM organizations WHERE id=?", (org,)).fetchone()["kind"] == "hotel":
        stay = {"staying": 0, "checkin_today": 0, "checkout_today": 0, "upcoming": 0}
        for r in db.execute("SELECT stay_start, stay_end FROM dogs WHERE org_id=? AND attending=1 AND stay_start IS NOT NULL", (org,)):
            f = stay_fields(r["stay_start"], r["stay_end"])
            stay["staying"] += f["stay_status"] in ("staying", "checkout_today")
            stay["upcoming"] += f["stay_status"] == "upcoming"
            stay["checkin_today"] += f["checkin_today"]
            stay["checkout_today"] += f["checkout_today"]
    return {"date": today_prefix(), "weekday": wd, "attending_dogs": dogs, "attendance": att, "counts": dict(c), "stay": stay,
            "tasks": [task_dict(t) for t in tasks]}

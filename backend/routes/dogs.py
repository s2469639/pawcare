import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..database import get_db, now_iso
from ..deps import current_staff, get_dog_or_404
from ..schemas import DogPatch
from .common import TASK_SELECT, dog_dict, task_dict, today_prefix

router = APIRouter(prefix="/api/dogs", tags=["dogs"])


def _record_view(db, org_id: int, dog_id: int, scope: str):
    sql = ("SELECT r.*, s.name AS author_name, s.role AS author_role FROM care_records r "
           "JOIN staff s ON s.id=r.author_id WHERE r.org_id=? AND r.dog_id=?")
    args = [org_id, dog_id]
    if scope == "today":
        sql += " AND r.observed_at LIKE ?"
        args.append(today_prefix() + "%")
    rows = [dict(x) for x in db.execute(sql + " ORDER BY r.observed_at DESC, r.id DESC", args)]
    for rec in rows:
        rec["tasks"] = [dict(t) for t in db.execute(
            "SELECT id,title,acknowledgment_status,action_status FROM tasks WHERE source_record_id=? ORDER BY id",
            (rec["id"],))]
    return rows


@router.get("")
def list_dogs(q: str = "", status: str = Query("all", pattern="^(all|needs_check|has_task|clear)$"),
              staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    dogs = []
    for r in db.execute("SELECT * FROM dogs WHERE org_id=? AND name LIKE ? ORDER BY id",
                        (staff["org_id"], f"%{q.strip()}%")):
        d = dog_dict(r)
        counts = db.execute(
            "SELECT SUM(acknowledgment_status='pending' AND action_status!='completed') AS pend,"
            " SUM(action_status!='completed') AS open FROM tasks WHERE dog_id=?", (d["id"],)).fetchone()
        d["needs_check_count"], d["open_task_count"] = counts["pend"] or 0, counts["open"] or 0
        last = db.execute(
            "SELECT record_type,structured_value,content,observed_at FROM care_records WHERE dog_id=? AND observed_at LIKE ?"
            " ORDER BY observed_at DESC, id DESC LIMIT 1", (d["id"], today_prefix() + "%")).fetchone()
        d["today_status"] = None if last is None else dict(last)
        d["caution"] = next((d["care_context"].get(k) for k in ("sensitivity", "owner_request", "behavior")
                             if d["care_context"].get(k)), None)
        dogs.append(d)
    if status == "needs_check":
        dogs = [d for d in dogs if d["needs_check_count"] > 0]
    elif status == "has_task":
        dogs = [d for d in dogs if d["open_task_count"] > 0]
    elif status == "clear":
        dogs = [d for d in dogs if d["open_task_count"] == 0]
    return dogs


@router.get("/{dog_id}")
def get_dog(dog_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    d = dog_dict(get_dog_or_404(db, dog_id, staff["org_id"]))
    tasks = db.execute(TASK_SELECT + " WHERE t.dog_id=? ORDER BY rank_order, prio_order, t.created_at DESC", (dog_id,))
    d["tasks"] = [task_dict(t) for t in tasks]
    d["records_today"] = _record_view(db, staff["org_id"], dog_id, "today")
    return d


@router.get("/{dog_id}/records")
def dog_records(dog_id: int, scope: str = Query("today", pattern="^(today|all)$"),
                staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    get_dog_or_404(db, dog_id, staff["org_id"])
    return _record_view(db, staff["org_id"], dog_id, scope)


@router.patch("/{dog_id}")
def patch_dog(dog_id: int, body: DogPatch, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    cur = get_dog_or_404(db, dog_id, staff["org_id"])
    data = body.model_dump(exclude_unset=True)
    if "care_context" in data and data["care_context"] is not None:
        merged = {**json.loads(cur["care_context"] or "{}"), **data["care_context"]}
        data["care_context"] = json.dumps(merged, ensure_ascii=False)
    if "attending" in data and data["attending"] is not None:
        data["attending"] = int(data["attending"])
    data = {k: v for k, v in data.items() if v is not None}
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        db.execute(f"UPDATE dogs SET {sets} WHERE id=?", (*data.values(), dog_id))
    return dog_dict(db.execute("SELECT * FROM dogs WHERE id=?", (dog_id,)).fetchone())

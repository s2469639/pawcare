import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import block_for, get_db, now_iso
from ..deps import current_staff, get_dog_or_404, get_staff_in_org
from ..schemas import ApprovalBody, RecordCreate
from .common import today_prefix
from .media import attach_media

router = APIRouter(prefix="/api/records", tags=["records"])

BASE = ("SELECT r.*, d.name AS dog_name, s.name AS author_name, s.role AS author_role, b.name AS block_name "
        "FROM care_records r JOIN dogs d ON d.id=r.dog_id JOIN staff s ON s.id=r.author_id "
        "LEFT JOIN routine_blocks b ON b.id=r.block_id ")


@router.get("")
def list_records(scope: str = Query("today", pattern="^(today|all)$"), unlinked: bool = False,
                 staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    sql, args = BASE + "WHERE r.org_id=?", [staff["org_id"]]
    if scope == "today":
        sql += " AND r.observed_at LIKE ?"
        args.append(today_prefix() + "%")
    if unlinked:
        sql += " AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.source_record_id=r.id)"
    return attach_media(db, [dict(r) for r in db.execute(sql + " ORDER BY r.observed_at DESC, r.id DESC", args)])


@router.get("/{record_id}")
def get_record(record_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    r = db.execute(BASE + "WHERE r.id=? AND r.org_id=?", (record_id, staff["org_id"])).fetchone()
    if r is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return attach_media(db, [dict(r)])[0]


@router.post("", status_code=201)
def create_record(body: RecordCreate, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    get_dog_or_404(db, body.dog_id, staff["org_id"])
    sv = body.structured_value
    content = body.content or (sv or "")
    if not content:
        raise HTTPException(422, "기록 내용 또는 관찰 값을 입력해 주세요.")
    if body.structured_value == "직접 입력" and not body.content:
        raise HTTPException(422, "'직접 입력'을 선택한 경우 상세 내용을 입력해 주세요.")
    author_id = body.author_id or staff["id"]
    get_staff_in_org(db, author_id, staff["org_id"])
    now = now_iso()
    observed = body.observed_at or now
    blocks = [dict(b) for b in db.execute("SELECT * FROM routine_blocks WHERE org_id=? ORDER BY sort_order", (staff["org_id"],))]
    if body.block_id is not None and body.block_id not in {b["id"] for b in blocks}:
        raise HTTPException(422, "일과 구간을 찾을 수 없습니다.")
    block_id = body.block_id if body.block_id is not None else block_for(blocks, observed)
    cur = db.execute(
        "INSERT INTO care_records(org_id,dog_id,author_id,record_type,structured_value,content,observed_at,created_at,block_id)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (staff["org_id"], body.dog_id, author_id, body.record_type, sv, content, observed, now, block_id))
    return attach_media(db, [dict(db.execute(BASE + "WHERE r.id=?", (cur.lastrowid,)).fetchone())])[0]


@router.patch("/{record_id}/parent-approval")
def parent_approval(record_id: int, body: ApprovalBody, staff=Depends(current_staff),
                    db: sqlite3.Connection = Depends(get_db)):
    r = db.execute("SELECT * FROM care_records WHERE id=? AND org_id=?", (record_id, staff["org_id"])).fetchone()
    if r is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    if body.action == "approve":
        if not body.parent_text:
            raise HTTPException(422, "보호자에게 보여줄 문구를 입력해 주세요.")
        db.execute("UPDATE care_records SET parent_status='approved', parent_text=?, parent_approved_by=?,"
                   " parent_approved_at=? WHERE id=?", (body.parent_text, staff["id"], now_iso(), record_id))
    else:
        db.execute("UPDATE care_records SET parent_status='private', parent_text=NULL, parent_approved_by=NULL,"
                   " parent_approved_at=NULL WHERE id=?", (record_id,))
    return dict(db.execute(BASE + "WHERE r.id=?", (record_id,)).fetchone())

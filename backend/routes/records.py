import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import block_for, get_db, now_iso, now_precise
from ..deps import FieldError, current_staff, get_dog_or_404, get_staff_in_org
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
    dog = get_dog_or_404(db, body.dog_id, staff["org_id"])
    if not dog["attending"]:
        raise HTTPException(409, f"{dog['name']}은(는) 퇴원 처리되어 새 기록을 남길 수 없습니다.")
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
    """보호자 공개 승인/취소. 공개 대상은 '반려견별'로 저장한다: 사진은 직원이 고른 아이의 보호자에게만 보이고,
    글(parent_text)은 기록의 반려견 보호자에게만 보인다(다른 아이의 글이 새지 않게)."""
    r = db.execute("SELECT * FROM care_records WHERE id=? AND org_id=?", (record_id, staff["org_id"])).fetchone()
    if r is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    media_ids = [m["id"] for m in db.execute("SELECT id FROM media WHERE record_id=?", (record_id,))]
    if media_ids:
        db.execute(f"DELETE FROM media_shares WHERE media_id IN ({','.join('?' * len(media_ids))})", media_ids)   # 승인 내용은 항상 새로 정한다
    if body.action == "revoke":
        db.execute("UPDATE care_records SET parent_status='private', parent_text=NULL, parent_approved_by=NULL,"
                   " parent_approved_at=NULL WHERE id=?", (record_id,))
        return attach_media(db, [dict(db.execute(BASE + "WHERE r.id=?", (record_id,)).fetchone())])[0]
    text = (body.parent_text or "").strip()
    shares: list[tuple[int, int]] = []
    seen = set()
    for m in body.media:
        if m.media_id not in media_ids:
            raise HTTPException(422, "이 기록에 첨부된 사진이 아닙니다.")
        if m.media_id in seen:
            raise HTTPException(422, "같은 사진이 중복 선택되었습니다.")
        seen.add(m.media_id)
        tagged = {x["dog_id"] for x in db.execute("SELECT dog_id FROM media_dogs WHERE media_id=?", (m.media_id,))}
        for dog_id in sorted(set(m.dog_ids)):
            if dog_id not in tagged:
                raise HTTPException(422, "사진에 태그되지 않은 반려견의 보호자에게는 공개할 수 없습니다.")
            shares.append((m.media_id, dog_id))
    if not text and not shares:
        raise FieldError("parent_text", "보호자에게 보여줄 문구를 입력하거나 공개할 사진을 선택해 주세요.")
    # 동의가 확인되지 않았거나 퇴원한 반려견의 자료는 공개할 수 없다
    for dog_id in {r["dog_id"]} | {d for _, d in shares}:
        dog = db.execute("SELECT name, consent_at, attending FROM dogs WHERE id=? AND org_id=?", (dog_id, staff["org_id"])).fetchone()
        if dog is None:
            raise HTTPException(404, "반려견을 찾을 수 없습니다.")
        if not dog["consent_at"]:
            raise HTTPException(409, f"{dog['name']}의 보호자 동의가 확인되지 않아 공개할 수 없습니다. 반려견 프로필에서 동의 확인을 기록해 주세요.")
        if not dog["attending"]:
            raise HTTPException(409, f"{dog['name']}은(는) 퇴원 처리되어 새로 공개할 수 없습니다.")
    now = now_precise()
    db.execute("UPDATE care_records SET parent_status='approved', parent_text=?, parent_approved_by=?, parent_approved_at=? WHERE id=?",
               (text, staff["id"], now, record_id))
    db.executemany("INSERT INTO media_shares(media_id,dog_id,approved_by,approved_at) VALUES (?,?,?,?)",
                   [(mid, did, staff["id"], now) for mid, did in shares])
    return attach_media(db, [dict(db.execute(BASE + "WHERE r.id=?", (record_id,)).fetchone())])[0]

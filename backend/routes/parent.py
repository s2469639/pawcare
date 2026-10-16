"""보호자 전용 API. 모든 응답은 '이 보호자에게 연결된 반려견'과 '직원이 공개 승인한 내용'으로만 구성한다."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..database import get_db, now_precise, upload_dir
from ..deps import current_parent
from .common import dog_dict

router = APIRouter(prefix="/api/parent", tags=["parent"])


def _own_dog_ids(db, parent) -> list[int]:
    return [r["dog_id"] for r in db.execute("SELECT dog_id FROM guardian_dogs WHERE account_id=?", (parent["id"],))]


def _shared_media(db, dog_id: int, record_id: int):
    """이 반려견에게 공개된 사진(해당 기록에 첨부된 것). 승인된 기록의 것만."""
    return [{"id": m["id"], "width": m["width"], "height": m["height"]} for m in db.execute(
        "SELECT m.id, m.width, m.height FROM media_shares s JOIN media m ON m.id=s.media_id "
        "JOIN care_records r ON r.id=m.record_id "
        "WHERE s.dog_id=? AND m.record_id=? AND r.parent_status='approved' ORDER BY m.id", (dog_id, record_id))]


def _feed_times(db, dog_id: int) -> list[str]:
    """알림장 항목(이 아이의 승인 기록 + 다른 아이 기록에 찍힌 단체 사진이 속한 기록)의 공개 시각들."""
    times = [r["parent_approved_at"] for r in db.execute(
        "SELECT parent_approved_at FROM care_records WHERE dog_id=? AND parent_status='approved'", (dog_id,))]
    times += [r["t"] for r in db.execute(
        "SELECT DISTINCT r.id, r.parent_approved_at AS t FROM media_shares s JOIN media m ON m.id=s.media_id "
        "JOIN care_records r ON r.id=m.record_id WHERE s.dog_id=? AND r.dog_id!=? AND r.parent_status='approved'", (dog_id, dog_id))]
    return times


def _seen_at(db, parent, dog_id: int):
    r = db.execute("SELECT seen_at FROM parent_reads WHERE account_id=? AND dog_id=?", (parent["id"], dog_id)).fetchone()
    return r["seen_at"] if r else None


def _unseen(db, parent, dog_id: int) -> int:
    seen = _seen_at(db, parent, dog_id)
    return sum(1 for t in _feed_times(db, dog_id) if seen is None or t > seen)


@router.get("/dogs")
def parent_dogs(parent=Depends(current_parent), db: sqlite3.Connection = Depends(get_db)):
    """보호자 본인에게 연결된 반려견만. 내부 정보는 포함하지 않는다."""
    return [{"id": r["id"], "name": r["name"], "breed": r["breed"], "avatar_color": r["avatar_color"], "photo": r["photo"],
             "unseen": _unseen(db, parent, r["id"])}      # 앱 안에서만 보이는 '새 알림장' 개수(푸시 알림 아님)
            for r in db.execute("SELECT d.* FROM guardian_dogs g JOIN dogs d ON d.id=g.dog_id WHERE g.account_id=? ORDER BY d.id", (parent["id"],))]


@router.get("/dogs/{dog_id}/preview")
def parent_preview(dog_id: int, parent=Depends(current_parent), db: sqlite3.Connection = Depends(get_db)):
    """알림장: ① 이 아이의 승인된 기록(글+이 아이에게 공개된 사진) ② 다른 아이의 기록에 찍힌 단체 사진(사진만, 글은 제외)."""
    dog = db.execute("SELECT d.* FROM guardian_dogs g JOIN dogs d ON d.id=g.dog_id WHERE g.account_id=? AND d.id=?",
                     (parent["id"], dog_id)).fetchone()
    if dog is None:
        raise HTTPException(404, "반려견을 찾을 수 없습니다.")      # 남의 아이와 없는 아이를 구분하지 않는다
    seen = _seen_at(db, parent, dog_id)
    is_new = lambda t: seen is None or t > seen
    recs = [dict(r) | {"media": _shared_media(db, dog_id, r["id"]), "is_new": is_new(r["parent_approved_at"])} for r in db.execute(
        "SELECT id, record_type, parent_text, parent_approved_at FROM care_records "
        "WHERE dog_id=? AND parent_status='approved' ORDER BY observed_at DESC, id DESC", (dog_id,))]
    group = [dict(m) | {"is_new": is_new(m["shared_at"])} for m in db.execute(
        "SELECT m.id, m.width, m.height, r.parent_approved_at AS shared_at FROM media_shares s JOIN media m ON m.id=s.media_id "
        "JOIN care_records r ON r.id=m.record_id WHERE s.dog_id=? AND r.dog_id!=? AND r.parent_status='approved' "
        "ORDER BY r.parent_approved_at DESC, m.id", (dog_id, dog_id))]
    d = dog_dict(dog)
    return {"dog": {"id": d["id"], "name": d["name"], "breed": d["breed"], "age_text": d["age_text"],
                    "avatar_color": d["avatar_color"], "photo": d["photo"]},
            "records": recs, "group_photos": group, "previous_seen_at": seen}


@router.post("/dogs/{dog_id}/seen")
def mark_seen(dog_id: int, parent=Depends(current_parent), db: sqlite3.Connection = Depends(get_db)):
    """알림장을 열어 봤음을 기록한다(새 알림장 표시 해제)."""
    if dog_id not in _own_dog_ids(db, parent):
        raise HTTPException(404, "반려견을 찾을 수 없습니다.")
    db.execute("INSERT INTO parent_reads(account_id,dog_id,seen_at) VALUES (?,?,?) "
               "ON CONFLICT(account_id,dog_id) DO UPDATE SET seen_at=excluded.seen_at", (parent["id"], dog_id, now_precise()))
    return {"unseen": 0}


@router.get("/media/{media_id}/file")
def parent_media_file(media_id: int, size: str = Query("full", pattern="^(full|thumb)$"), parent=Depends(current_parent),
                      db: sqlite3.Connection = Depends(get_db)):
    """공개된 사진 파일. 이 보호자의 반려견에게 공개되었고 기록이 승인 상태일 때만(아니면 존재 여부도 알리지 않는 404)."""
    own = _own_dog_ids(db, parent)
    row = None
    if own:
        row = db.execute(
            f"SELECT m.* FROM media m JOIN care_records r ON r.id=m.record_id WHERE m.id=? AND r.parent_status='approved' "
            f"AND EXISTS (SELECT 1 FROM media_shares s WHERE s.media_id=m.id AND s.dog_id IN ({','.join('?' * len(own))}))",
            (media_id, *own)).fetchone()
    if row is None:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    path = upload_dir() / "media" / str(row["org_id"]) / (row["thumb"] if size == "thumb" else row["file"])
    if not path.is_file():
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})

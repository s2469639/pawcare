import json
import secrets
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..database import get_db, now_iso, upload_dir
from ..deps import current_staff, get_dog_or_404
from ..schemas import DogCreate, DogPatch
from .common import TASK_SELECT, dog_dict, task_dict, today_prefix
from .media import attach_media

router = APIRouter(prefix="/api/dogs", tags=["dogs"])


def _record_view(db, org_id: int, dog_id: int, scope: str):
    sql = ("SELECT r.*, s.name AS author_name, s.role AS author_role, b.name AS block_name FROM care_records r "
           "JOIN staff s ON s.id=r.author_id LEFT JOIN routine_blocks b ON b.id=r.block_id WHERE r.org_id=? AND r.dog_id=?")
    args = [org_id, dog_id]
    if scope == "today":
        sql += " AND r.observed_at LIKE ?"
        args.append(today_prefix() + "%")
    rows = [dict(x) for x in db.execute(sql + " ORDER BY r.observed_at DESC, r.id DESC", args)]
    for rec in rows:
        rec["tasks"] = [dict(t) for t in db.execute(
            "SELECT id,title,acknowledgment_status,action_status FROM tasks WHERE source_record_id=? ORDER BY id",
            (rec["id"],))]
    return attach_media(db, rows)


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


AVATAR_COLORS = ["#C98D72", "#A5AE98", "#8E9A82", "#7C6F64", "#B8A58C", "#9A8F7E"]
MAX_PHOTO = 1_000_000
PHOTO_TYPES = {"image/webp": "webp", "image/jpeg": "jpg", "image/png": "png"}


def _sniff(data: bytes):
    """파일 앞부분(매직 넘버)으로 실제 이미지 형식을 판별한다. Content-Type만 믿지 않는다."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


def _remove_uploaded(photo: Optional[str]):
    if photo and photo.startswith("uploads/dogs/"):
        (upload_dir() / "dogs" / photo.rsplit("/", 1)[1]).unlink(missing_ok=True)


@router.post("", status_code=201)
def create_dog(body: DogCreate, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org = staff["org_id"]
    if db.execute("SELECT 1 FROM dogs WHERE org_id=? AND name=? AND owner_name=?", (org, body.name, body.owner_name)).fetchone():
        raise HTTPException(409, f"이미 등록된 반려견입니다. ({body.name} · 보호자 {body.owner_name})")
    ctx = {k: "" for k in ("meal", "sensitivity", "behavior", "owner_request", "other")}
    ctx.update(body.care_context or {})
    n = db.execute("SELECT COUNT(*) FROM dogs WHERE org_id=?", (org,)).fetchone()[0]
    cur = db.execute(
        "INSERT INTO dogs(org_id,name,breed,birth_date,avatar_color,owner_name,care_context) VALUES (?,?,?,?,?,?,?)",
        (org, body.name, body.breed, body.birth_date, AVATAR_COLORS[n % len(AVATAR_COLORS)], body.owner_name,
         json.dumps(ctx, ensure_ascii=False)))
    return dog_dict(db.execute("SELECT * FROM dogs WHERE id=?", (cur.lastrowid,)).fetchone())


@router.post("/{dog_id}/photo")
async def upload_photo(dog_id: int, request: Request, staff=Depends(current_staff),
                       db: sqlite3.Connection = Depends(get_db)):
    """원본 이미지 바이트를 그대로 받는다. 브라우저에서 정사각형(512px)으로 잘라 보내는 것을 전제로 한다."""
    dog = get_dog_or_404(db, dog_id, staff["org_id"])
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in PHOTO_TYPES:
        raise HTTPException(415, "JPG, PNG, WebP 형식의 사진만 올릴 수 있습니다.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_PHOTO:
        raise HTTPException(413, "사진 용량은 1MB 이하여야 합니다.")
    data = await request.body()
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "사진 용량은 1MB 이하여야 합니다.")
    if _sniff(data) != ctype:
        raise HTTPException(415, "사진 파일이 올바르지 않습니다. 다른 사진을 선택해 주세요.")
    folder = upload_dir() / "dogs"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{dog_id}-{secrets.token_hex(6)}.{PHOTO_TYPES[ctype]}"
    (folder / name).write_bytes(data)
    _remove_uploaded(dog["photo"])
    db.execute("UPDATE dogs SET photo=? WHERE id=?", (f"uploads/dogs/{name}", dog_id))
    return dog_dict(db.execute("SELECT * FROM dogs WHERE id=?", (dog_id,)).fetchone())


@router.delete("/{dog_id}/photo")
def delete_photo(dog_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    dog = get_dog_or_404(db, dog_id, staff["org_id"])
    _remove_uploaded(dog["photo"])
    db.execute("UPDATE dogs SET photo=NULL WHERE id=?", (dog_id,))
    return dog_dict(db.execute("SELECT * FROM dogs WHERE id=?", (dog_id,)).fetchone())

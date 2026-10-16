"""기록에 첨부하는 사진. 직원(같은 유치원)만 올리고 볼 수 있다. 보호자 공개는 M3 이후."""
import secrets
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import imaging
from ..database import get_db, now_iso, upload_dir
from ..deps import current_staff, get_dog_or_404

router = APIRouter(prefix="/api", tags=["media"])

MAX_BYTES = 2_000_000
MAX_PER_RECORD = 10
TYPES = {"image/jpeg", "image/png", "image/webp"}


class TagBody(BaseModel):
    dog_ids: list[int]


def _folder(org_id: int):
    f = upload_dir() / "media" / str(org_id)
    f.mkdir(parents=True, exist_ok=True)
    return f


def _parse_dogs(db, raw: Optional[str], org_id: int, default: int) -> list[int]:
    if raw is None or raw.strip() == "":
        return [default]
    try:
        ids = sorted({int(x) for x in raw.split(",") if x.strip()})
    except ValueError:
        raise HTTPException(422, "태그할 반려견 형식이 올바르지 않습니다.")
    return _check_dogs(db, ids, org_id)


def _check_dogs(db, ids: list[int], org_id: int, existing: Optional[set] = None) -> list[int]:
    """태그할 반려견 검증. 퇴원 처리된 아이는 새로 태그할 수 없다(이미 태그된 것을 유지하는 것은 허용)."""
    ids = sorted(set(ids))
    if not ids:
        raise HTTPException(422, "사진에 찍힌 반려견을 한 마리 이상 선택해 주세요.")
    if len(ids) > 20:
        raise HTTPException(422, "한 번에 태그할 수 있는 반려견 수를 넘었습니다.")
    for i in ids:
        dog = get_dog_or_404(db, i, org_id)       # 다른 유치원 반려견이면 404
        if not dog["attending"] and i not in (existing or set()):
            raise HTTPException(409, f"{dog['name']}은(는) 퇴원 처리되어 새 사진을 태그할 수 없습니다.")
    return ids


def media_view(db, rows) -> list[dict]:
    out = []
    for r in rows:
        dogs = db.execute("SELECT d.id, d.name FROM media_dogs m JOIN dogs d ON d.id=m.dog_id WHERE m.media_id=? ORDER BY d.id", (r["id"],)).fetchall()
        shared = [x["dog_id"] for x in db.execute("SELECT dog_id FROM media_shares WHERE media_id=? ORDER BY dog_id", (r["id"],))]
        out.append({"id": r["id"], "record_id": r["record_id"], "width": r["width"], "height": r["height"], "created_at": r["created_at"],
                    "uploaded_by": r["uploaded_by"], "dog_ids": [d["id"] for d in dogs], "dog_names": [d["name"] for d in dogs],
                    "shared_dog_ids": shared})
    return out


def attach_media(db, records: list[dict]) -> list[dict]:
    """기록 목록에 사진 목록(media)을 붙인다."""
    for rec in records:
        rows = db.execute("SELECT * FROM media WHERE record_id=? ORDER BY id", (rec["id"],)).fetchall()
        rec["media"] = media_view(db, rows)
    return records


def _get_media(db, media_id: int, org_id: int):
    r = db.execute("SELECT * FROM media WHERE id=? AND org_id=?", (media_id, org_id)).fetchone()
    if r is None:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    return r


@router.post("/records/{record_id}/media", status_code=201)
async def upload_media(record_id: int, request: Request, dog_ids: Optional[str] = Query(default=None),
                       staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """사진 한 장(원본 바이트)을 기록에 첨부한다. dog_ids=1,2 로 찍힌 반려견을 태그(기본: 기록의 반려견)."""
    rec = db.execute("SELECT id, dog_id FROM care_records WHERE id=? AND org_id=?", (record_id, staff["org_id"])).fetchone()
    if rec is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    owner = db.execute("SELECT name, attending FROM dogs WHERE id=?", (rec["dog_id"],)).fetchone()
    if not owner["attending"]:
        raise HTTPException(409, f"{owner['name']}은(는) 퇴원 처리되어 새 사진을 올릴 수 없습니다.")
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in TYPES:
        raise HTTPException(415, "JPG, PNG, WebP 사진만 올릴 수 있습니다.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(413, "사진 용량은 2MB 이하여야 합니다.")
    tags = _parse_dogs(db, dog_ids, staff["org_id"], rec["dog_id"])
    if db.execute("SELECT COUNT(*) FROM media WHERE record_id=?", (record_id,)).fetchone()[0] >= MAX_PER_RECORD:
        raise HTTPException(409, f"한 기록에는 사진을 최대 {MAX_PER_RECORD}장까지 첨부할 수 있습니다.")
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "사진 용량은 2MB 이하여야 합니다.")
    try:
        img = imaging.process_photo(data)
    except imaging.TooBig as e:
        raise HTTPException(413, str(e))
    except imaging.BadImage as e:
        raise HTTPException(415, str(e))
    folder = _folder(staff["org_id"])
    token = secrets.token_hex(12)
    full_name, thumb_name = f"{token}.webp", f"{token}-t.webp"
    (folder / full_name).write_bytes(img["full"])
    (folder / thumb_name).write_bytes(img["thumb"])
    try:
        cur = db.execute("INSERT INTO media(org_id,record_id,file,thumb,width,height,bytes,uploaded_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (staff["org_id"], record_id, full_name, thumb_name, img["width"], img["height"], len(img["full"]), staff["id"], now_iso()))
        db.executemany("INSERT INTO media_dogs(media_id,dog_id) VALUES (?,?)", [(cur.lastrowid, d) for d in tags])
    except Exception:
        (folder / full_name).unlink(missing_ok=True); (folder / thumb_name).unlink(missing_ok=True)
        raise
    return media_view(db, [db.execute("SELECT * FROM media WHERE id=?", (cur.lastrowid,)).fetchone()])[0]


@router.get("/records/{record_id}/media")
def list_media(record_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    if db.execute("SELECT 1 FROM care_records WHERE id=? AND org_id=?", (record_id, staff["org_id"])).fetchone() is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return media_view(db, db.execute("SELECT * FROM media WHERE record_id=? ORDER BY id", (record_id,)).fetchall())


@router.get("/dogs/{dog_id}/media")
def dog_media(dog_id: int, scope: str = Query("today", pattern="^(today|all)$"), staff=Depends(current_staff),
              db: sqlite3.Connection = Depends(get_db)):
    """이 반려견이 태그된 사진(다른 아이의 기록에 첨부된 단체 사진 포함)."""
    from .common import today_prefix
    get_dog_or_404(db, dog_id, staff["org_id"])
    sql = ("SELECT m.* FROM media m JOIN media_dogs md ON md.media_id=m.id WHERE md.dog_id=? AND m.org_id=?")
    args: list = [dog_id, staff["org_id"]]
    if scope == "today":
        sql += " AND m.created_at LIKE ?"
        args.append(today_prefix() + "%")
    return media_view(db, db.execute(sql + " ORDER BY m.id DESC", args).fetchall())


@router.get("/media/{media_id}/file")
def media_file(media_id: int, size: str = Query("full", pattern="^(full|thumb)$"), staff=Depends(current_staff),
               db: sqlite3.Connection = Depends(get_db)):
    r = _get_media(db, media_id, staff["org_id"])
    path = upload_dir() / "media" / str(r["org_id"]) / (r["thumb"] if size == "thumb" else r["file"])
    if not path.is_file():
        raise HTTPException(404, "사진 파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.patch("/media/{media_id}")
def tag_media(media_id: int, body: TagBody, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    r = _get_media(db, media_id, staff["org_id"])
    before = {x["dog_id"] for x in db.execute("SELECT dog_id FROM media_dogs WHERE media_id=?", (media_id,))}
    ids = _check_dogs(db, body.dog_ids, staff["org_id"], existing=before)
    db.execute("DELETE FROM media_dogs WHERE media_id=?", (media_id,))
    db.executemany("INSERT INTO media_dogs(media_id,dog_id) VALUES (?,?)", [(media_id, d) for d in ids])
    # 사진에서 태그가 빠진 아이의 보호자에게는 더 이상 공개하지 않는다(공개 대상은 항상 태그된 아이의 부분집합)
    db.execute(f"DELETE FROM media_shares WHERE media_id=? AND dog_id NOT IN ({','.join('?' * len(ids))})", (media_id, *ids))
    return media_view(db, [r])[0]


@router.delete("/media/{media_id}")
def delete_media(media_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    r = _get_media(db, media_id, staff["org_id"])
    folder = upload_dir() / "media" / str(r["org_id"])
    db.execute("DELETE FROM media WHERE id=?", (media_id,))
    (folder / r["file"]).unlink(missing_ok=True)
    (folder / r["thumb"]).unlink(missing_ok=True)
    return {"ok": True}

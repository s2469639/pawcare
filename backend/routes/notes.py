"""직원 개인 메모. 작성한 직원 본인에게만 보이며 관리자·다른 직원·보호자는 읽을 수 없다(다른 사람의 메모는 404)."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..database import get_db, now_iso
from ..deps import current_staff

router = APIRouter(prefix="/api/notes", tags=["notes"])
MAX_NOTES = 100


class NoteIn(BaseModel):
    body: str = Field(max_length=1000)

    @field_validator("body")
    @classmethod
    def _body(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("메모 내용을 입력해 주세요.")
        return v


def _own(db, note_id: int, staff_id: int):
    r = db.execute("SELECT * FROM staff_notes WHERE id=? AND staff_id=?", (note_id, staff_id)).fetchone()
    if r is None:
        raise HTTPException(404, "메모를 찾을 수 없습니다.")
    return r


@router.get("")
def list_notes(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        "SELECT id, body, created_at, updated_at FROM staff_notes WHERE staff_id=? ORDER BY updated_at DESC, id DESC", (staff["id"],))]


@router.post("", status_code=201)
def create_note(body: NoteIn, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    if db.execute("SELECT COUNT(*) FROM staff_notes WHERE staff_id=?", (staff["id"],)).fetchone()[0] >= MAX_NOTES:
        raise HTTPException(422, f"메모는 최대 {MAX_NOTES}개까지 저장할 수 있습니다. 오래된 메모를 지워 주세요.")
    now = now_iso()
    cur = db.execute("INSERT INTO staff_notes(staff_id,body,created_at,updated_at) VALUES (?,?,?,?)", (staff["id"], body.body, now, now))
    return dict(_own(db, cur.lastrowid, staff["id"]))


@router.patch("/{note_id}")
def update_note(note_id: int, body: NoteIn, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    _own(db, note_id, staff["id"])
    db.execute("UPDATE staff_notes SET body=?, updated_at=? WHERE id=?", (body.body, now_iso(), note_id))
    return dict(_own(db, note_id, staff["id"]))


@router.delete("/{note_id}")
def delete_note(note_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    _own(db, note_id, staff["id"])
    db.execute("DELETE FROM staff_notes WHERE id=?", (note_id,))
    return {"ok": True}

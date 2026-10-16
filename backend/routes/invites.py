"""보호자 초대 코드(직원 전용). 코드 원문은 만든 직후 한 번만 보여주고 DB에는 해시만 저장한다."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth
from ..database import get_db, now_iso
from ..deps import current_staff, get_dog_or_404

router = APIRouter(prefix="/api", tags=["invites"])


class InviteCreate(BaseModel):
    dog_id: int


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


@router.post("/invites", status_code=201)
def create_invite(body: InviteCreate, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    dog = get_dog_or_404(db, body.dog_id, staff["org_id"])
    for _ in range(5):    # 해시 충돌(사실상 없음) 대비
        code = auth.new_code()
        try:
            cur = db.execute("INSERT INTO invites(code_hash,org_id,dog_id,created_by,created_at,expires_at) VALUES (?,?,?,?,?,?)",
                             (auth.hash_code(code), staff["org_id"], dog["id"], staff["id"], now_iso(), auth.invite_expiry()))
            break
        except sqlite3.IntegrityError:
            continue
    else:
        raise HTTPException(500, "초대 코드를 만들지 못했습니다. 다시 시도해 주세요.")
    inv = db.execute("SELECT expires_at FROM invites WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"id": cur.lastrowid, "code": code, "dog_id": dog["id"], "dog_name": dog["name"], "expires_at": inv["expires_at"]}


@router.get("/dogs/{dog_id}/guardians")
def guardians(dog_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    get_dog_or_404(db, dog_id, staff["org_id"])
    now = now_iso()
    people = [{"account_id": r["id"], "name": r["name"], "email": _mask(r["email"])} for r in db.execute(
        "SELECT a.id,a.name,a.email FROM guardian_dogs g JOIN accounts a ON a.id=g.account_id WHERE g.dog_id=? ORDER BY a.id", (dog_id,))]
    invs = []
    for r in db.execute("SELECT id,created_at,expires_at,used_at FROM invites WHERE dog_id=? AND org_id=? ORDER BY id DESC LIMIT 10",
                        (dog_id, staff["org_id"])):
        status = "used" if r["used_at"] else "expired" if r["expires_at"] <= now else "active"
        invs.append({**dict(r), "status": status})
    return {"guardians": people, "invites": invs}


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    r = db.execute("SELECT used_at FROM invites WHERE id=? AND org_id=?", (invite_id, staff["org_id"])).fetchone()
    if r is None:
        raise HTTPException(404, "초대 코드를 찾을 수 없습니다.")
    if r["used_at"]:
        raise HTTPException(409, "이미 사용된 초대 코드는 취소할 수 없습니다.")
    db.execute("DELETE FROM invites WHERE id=?", (invite_id,))
    return {"ok": True}

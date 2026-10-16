"""현재 직원 식별. 프로토타입에서는 X-Staff-Id 헤더(추후 로그인 토큰으로 교체되는 자리)."""
import sqlite3
from typing import Optional

from fastapi import Depends, Header, HTTPException

from .database import get_db


def current_staff(
    x_staff_id: Optional[str] = Header(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    if not x_staff_id or not x_staff_id.isdigit():
        raise HTTPException(401, "직원 정보가 필요합니다. 역할 선택 화면에서 다시 시작해 주세요.")
    r = db.execute("SELECT * FROM staff WHERE id=?", (int(x_staff_id),)).fetchone()
    if r is None:
        raise HTTPException(401, "알 수 없는 직원입니다. 역할 선택 화면에서 다시 시작해 주세요.")
    return dict(r)


def get_dog_or_404(db: sqlite3.Connection, dog_id: int, org_id: int) -> dict:
    r = db.execute("SELECT * FROM dogs WHERE id=? AND org_id=?", (dog_id, org_id)).fetchone()
    if r is None:
        raise HTTPException(404, "반려견을 찾을 수 없습니다.")
    return dict(r)


def get_staff_in_org(db: sqlite3.Connection, staff_id: int, org_id: int) -> dict:
    r = db.execute("SELECT * FROM staff WHERE id=? AND org_id=?", (staff_id, org_id)).fetchone()
    if r is None:
        raise HTTPException(422, "같은 유치원 소속 직원이 아닙니다.")
    return dict(r)

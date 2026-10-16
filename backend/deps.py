"""현재 사용자 식별. 세션 쿠키(브라우저) 또는 Authorization: Bearer(API 클라이언트·테스트)."""
import sqlite3

from fastapi import Depends, HTTPException, Request

from .auth import COOKIE, account_for_token
from .database import get_db

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class FieldError(Exception):
    """특정 입력칸에 연결해 보여줄 오류(프런트엔드가 해당 칸 아래에 표시)."""

    def __init__(self, field: str, message: str, status: int = 422):
        self.field, self.message, self.status = field, message, status


def session_token(request: Request):
    """(토큰, 출처). 명시적으로 보낸 Authorization: Bearer가 쿠키보다 우선한다(출처는 'bearer' 또는 'cookie')."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and auth[7:].strip():
        return auth[7:].strip(), "bearer"
    t = request.cookies.get(COOKIE)
    if t:
        return t, "cookie"
    return None, None


def current_account(request: Request, db: sqlite3.Connection = Depends(get_db)) -> dict:
    token, source = session_token(request)
    if not token:
        raise HTTPException(401, "로그인이 필요합니다.")
    acc = account_for_token(db, token)
    if acc is None:
        raise HTTPException(401, "로그인이 만료되었거나 올바르지 않습니다. 다시 로그인해 주세요.")
    # CSRF 방어: 쿠키로 인증된 상태 변경 요청은 커스텀 헤더가 있어야 한다(다른 사이트의 폼 전송은 이 헤더를 붙일 수 없음)
    if source == "cookie" and request.method not in SAFE_METHODS and request.headers.get("x-pawcare") != "1":
        raise HTTPException(403, "요청을 확인할 수 없습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.")
    return dict(acc)


def current_staff(account: dict = Depends(current_account), db: sqlite3.Connection = Depends(get_db)) -> dict:
    if account["role"] != "staff" or not account["staff_id"]:
        raise HTTPException(403, "직원 계정만 사용할 수 있습니다.")
    r = db.execute("SELECT * FROM staff WHERE id=?", (account["staff_id"],)).fetchone()
    if r is None:
        raise HTTPException(401, "직원 정보를 찾을 수 없습니다. 다시 로그인해 주세요.")
    return dict(r)


def current_parent(account: dict = Depends(current_account)) -> dict:
    if account["role"] != "parent":
        raise HTTPException(403, "보호자 계정만 사용할 수 있습니다.")
    return account


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

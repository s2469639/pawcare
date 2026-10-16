"""로그인·로그아웃·가입, 데모 모드 로그인."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth
from ..database import get_db, now_iso, now_precise
from ..deps import COOKIE, FieldError, session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

BAD_LOGIN = "이메일 또는 비밀번호가 올바르지 않습니다."


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class RegisterBody(BaseModel):
    code: str = Field(max_length=40)
    name: str = Field(min_length=1, max_length=30)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class DemoLoginBody(BaseModel):
    account_id: int


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_cookie(request: Request, response: Response, token: str) -> None:
    secure = request.url.scheme == "https" or auth.os.environ.get("COOKIE_SECURE") == "1"
    response.set_cookie(COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/")


def account_view(db: sqlite3.Connection, a: dict) -> dict:
    org = db.execute("SELECT name FROM organizations WHERE id=?", (a["org_id"],)).fetchone()
    v = {"id": a["id"], "name": a["name"], "email": a["email"], "role": a["role"], "org_id": a["org_id"],
         "org_name": org["name"] if org else "", "staff": None, "dogs": []}
    if a["role"] == "staff" and a["staff_id"]:
        s = db.execute("SELECT id,name,role,org_id FROM staff WHERE id=?", (a["staff_id"],)).fetchone()
        v["staff"] = dict(s) if s else None
    else:
        v["dogs"] = [dict(r) for r in db.execute(
            "SELECT d.id,d.name FROM guardian_dogs g JOIN dogs d ON d.id=g.dog_id WHERE g.account_id=? ORDER BY d.id", (a["id"],))]
    return v


def _blocked(db, request, email_key: str):
    wait = max(auth.retry_after(db, email_key, 5), auth.retry_after(db, f"ip:{_ip(request)}", 30))
    if wait:
        mins = -(-wait // 60)
        raise HTTPException(429, f"로그인 시도가 너무 많습니다. 약 {mins}분 후에 다시 시도해 주세요.", headers={"Retry-After": str(wait)})


@router.get("/config")
def config():
    return {"demo_mode": auth.demo_mode()}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    email = auth.normalize_email(body.email)
    key = f"login:{email}"
    _blocked(db, request, key)
    row = db.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
    ok = auth.verify_password(body.password, row["password_hash"] if row else auth.dummy_hash())
    if not row or not ok:
        auth.record_failure(db, key, f"ip:{_ip(request)}")
        raise HTTPException(401, BAD_LOGIN)    # 이메일이 없는 경우와 비밀번호가 틀린 경우를 구분하지 않는다
    auth.clear_failures(db, key)
    _set_cookie(request, response, auth.create_session(db, row["id"]))
    return {"account": account_view(db, dict(row))}


@router.post("/logout")
def logout(request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    token, _ = session_token(request)
    if token:
        auth.delete_session(db, token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """로그인 상태 확인. 로그인하지 않았거나 세션이 만료되었으면 오류가 아니라 account=null로 답한다."""
    token, _ = session_token(request)
    acc = auth.account_for_token(db, token) if token else None
    return {"account": account_view(db, dict(acc)) if acc else None}


@router.post("/register", status_code=201)
def register(body: RegisterBody, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    """보호자 가입: 직원이 만든 초대 코드가 있어야 한다. 코드 추측을 막기 위해 실패 횟수를 IP별로 제한한다."""
    ip_key = f"reg:{_ip(request)}"
    wait = auth.retry_after(db, ip_key, 10)
    if wait:
        raise HTTPException(429, f"시도가 너무 많습니다. 약 {-(-wait // 60)}분 후에 다시 시도해 주세요.", headers={"Retry-After": str(wait)})
    inv = db.execute("SELECT * FROM invites WHERE code_hash=?", (auth.hash_code(body.code),)).fetchone()
    if inv is None or inv["used_at"] or inv["expires_at"] <= now_iso():
        auth.record_failure(db, ip_key)
        raise FieldError("code", "초대 코드가 올바르지 않거나 이미 사용·만료되었습니다.", 400)
    email = auth.normalize_email(body.email)
    name = body.name.strip()
    if not name:
        raise FieldError("name", "이름을 입력해 주세요.")
    if not auth.EMAIL_RE.match(email):
        raise FieldError("email", "이메일 형식이 올바르지 않습니다.")
    msg = auth.check_password_policy(body.password, email)
    if msg:
        raise FieldError("password", msg)
    if db.execute("SELECT 1 FROM accounts WHERE email=?", (email,)).fetchone():
        raise FieldError("email", "이미 가입된 이메일입니다. 로그인해 주세요.", 409)
    # 코드를 먼저 '사용됨'으로 표시하고(조건부 UPDATE) 성공한 경우에만 계정을 만든다 → 동시 사용 방지
    used = db.execute("UPDATE invites SET used_at=? WHERE id=? AND used_at IS NULL AND expires_at > ?", (now_iso(), inv["id"], now_iso()))
    if used.rowcount != 1:
        raise FieldError("code", "초대 코드가 올바르지 않거나 이미 사용·만료되었습니다.", 400)
    cur = db.execute("INSERT INTO accounts(org_id,email,name,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                     (inv["org_id"], email, name, auth.hash_password(body.password), "parent", now_iso()))
    db.execute("INSERT INTO guardian_dogs(account_id,dog_id) VALUES (?,?)", (cur.lastrowid, inv["dog_id"]))
    db.execute("INSERT INTO parent_reads(account_id,dog_id,seen_at) VALUES (?,?,?)", (cur.lastrowid, inv["dog_id"], now_precise()))
    db.execute("UPDATE invites SET used_by=? WHERE id=?", (cur.lastrowid, inv["id"]))
    _set_cookie(request, response, auth.create_session(db, cur.lastrowid))
    row = db.execute("SELECT * FROM accounts WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"account": account_view(db, dict(row))}


# ---------------- 데모 모드 전용 ----------------
def require_demo() -> None:
    if not auth.demo_mode():
        raise HTTPException(404, "데모 모드에서만 사용할 수 있습니다.")


@router.get("/demo-accounts", dependencies=[Depends(require_demo)])
def demo_accounts(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT a.id, a.name, a.role, a.org_id, o.name AS org_name, s.role AS staff_role, "
        "(SELECT GROUP_CONCAT(d.name, ', ') FROM guardian_dogs g JOIN dogs d ON d.id=g.dog_id WHERE g.account_id=a.id) AS dogs "
        "FROM accounts a JOIN organizations o ON o.id=a.org_id LEFT JOIN staff s ON s.id=a.staff_id "
        "WHERE a.is_demo=1 ORDER BY a.org_id, a.role DESC, a.id")
    return [dict(r) for r in rows]


@router.post("/demo-login", dependencies=[Depends(require_demo)])
def demo_login(body: DemoLoginBody, request: Request, response: Response, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM accounts WHERE id=? AND is_demo=1", (body.account_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "데모 계정을 찾을 수 없습니다.")
    token, _ = session_token(request)
    if token:
        auth.delete_session(db, token)
    _set_cookie(request, response, auth.create_session(db, row["id"]))
    return {"account": account_view(db, dict(row))}

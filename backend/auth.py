"""인증 유틸: 비밀번호 해시, 세션, 초대 코드, 로그인 시도 제한. 표준 라이브러리만 사용한다."""
import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from .database import KST, now_iso

COOKIE = "pawcare_session"
SESSION_DAYS = 7
INVITE_DAYS = 7
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 헷갈리는 글자(I, L, O, 0, 1) 제외
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COMMON_PASSWORDS = {"password", "12345678", "123456789", "1234567890", "qwerty123", "password1", "11111111", "abcd1234", "iloveyou"}


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def demo_password() -> str:
    return os.environ.get("PAWCARE_DEMO_PASSWORD") or "pawcare-demo"


# ---------------- 비밀번호 ----------------
def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    """scrypt. 비용 인자는 해시 문자열에 함께 저장되므로 나중에 올려도 기존 해시가 검증된다."""
    n = int(os.environ.get("PAWCARE_SCRYPT_N") or 2 ** 15)
    r, p, salt = 8, 1, secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=256 * n * r, dklen=32)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(h)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=n, r=r, p=p, maxmem=256 * n * r, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


_dummy: Optional[str] = None


def dummy_hash() -> str:
    """존재하지 않는 이메일도 같은 시간이 걸리도록 비교용으로 쓰는 해시(계정 존재 여부 추측 방지)."""
    global _dummy
    if _dummy is None:
        _dummy = hash_password(secrets.token_hex(8))
    return _dummy


def check_password_policy(password: str, email: str = "") -> Optional[str]:
    if len(password) < 8:
        return "비밀번호는 8자 이상이어야 합니다."
    if len(password) > 128:
        return "비밀번호는 128자 이하여야 합니다."
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 3:
        return "너무 흔한 비밀번호입니다. 다른 비밀번호를 사용해 주세요."
    if email and password.lower() in {email.lower(), email.split("@")[0].lower()}:
        return "이메일과 같은 비밀번호는 사용할 수 없습니다."
    return None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# ---------------- 세션 ----------------
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _later(days: int) -> str:
    return (datetime.now(KST) + timedelta(days=days)).replace(microsecond=0, tzinfo=None).isoformat()


def create_session(db, account_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))   # 만료된 세션 정리
    db.execute("INSERT INTO sessions(token_hash,account_id,created_at,expires_at) VALUES (?,?,?,?)",
               (_hash_token(token), account_id, now_iso(), _later(SESSION_DAYS)))
    return token


def account_for_token(db, token: str):
    return db.execute(
        "SELECT a.* FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at > ?",
        (_hash_token(token), now_iso())).fetchone()


def delete_session(db, token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))


# ---------------- 초대 코드 ----------------
def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    return re.sub(r"[\s-]", "", (code or "")).upper()


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def invite_expiry() -> str:
    return _later(INVITE_DAYS)


# ---------------- 시도 횟수 제한 ----------------
WINDOW_MIN = 10


def _cutoff() -> str:
    return (datetime.now(KST) - timedelta(minutes=WINDOW_MIN)).replace(microsecond=0, tzinfo=None).isoformat()


def retry_after(db, key: str, limit: int) -> int:
    """제한에 걸렸다면 다시 시도할 수 있기까지 남은 초, 아니면 0."""
    rows = db.execute("SELECT at FROM login_attempts WHERE key=? AND at > ? ORDER BY at", (key, _cutoff())).fetchall()
    if len(rows) < limit:
        return 0
    oldest_that_matters = datetime.fromisoformat(rows[len(rows) - limit]["at"])
    free_at = oldest_that_matters + timedelta(minutes=WINDOW_MIN)
    return max(1, int((free_at - datetime.now(KST).replace(tzinfo=None)).total_seconds()))


def record_failure(db, *keys: str) -> None:
    db.executemany("INSERT INTO login_attempts(key,at) VALUES (?,?)", [(k, now_iso()) for k in keys])
    db.execute("DELETE FROM login_attempts WHERE at < ?", (_cutoff(),))
    db.commit()    # 요청이 오류로 끝나 롤백되어도 실패 기록은 남아야 한다


def clear_failures(db, key: str) -> None:
    db.execute("DELETE FROM login_attempts WHERE key=?", (key,))

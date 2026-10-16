import pytest
from fastapi.testclient import TestClient

# 테스트 편의: 직원·보호자별 인증 헤더(Authorization: Bearer 세션 토큰).
# 모듈 수준 dict를 fixture가 테스트마다 같은 객체 안에서 채워 넣는다.
MORNING, AFTERNOON, ADMIN, OTHER_ORG = {}, {}, {}, {}      # 직원 id 1, 2, 3, 4
PARENT_BORI, PARENT_TOFU, PARENT_MOCHA = {}, {}, {}        # 데모 보호자(김서연·박도윤·이수아)
DEMO_PASSWORD = "pawcare-demo"
_STAFF = {1: MORNING, 2: AFTERNOON, 3: ADMIN, 4: OTHER_ORG}
_PARENTS = {"보리": PARENT_BORI, "두부": PARENT_TOFU, "모카": PARENT_MOCHA}


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAWCARE_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("PAWCARE_UPLOADS", str(tmp_path / "uploads"))
    monkeypatch.setenv("PAWCARE_SCRYPT_N", "1024")          # 테스트에서는 해시 비용을 낮춰 빠르게
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    from backend import auth
    from backend.database import connect
    from backend.main import app
    with TestClient(app) as c:
        db = connect()
        try:
            for sid, hdr in _STAFF.items():
                acc = db.execute("SELECT id FROM accounts WHERE staff_id=?", (sid,)).fetchone()
                hdr.clear(); hdr.update(bearer(auth.create_session(db, acc["id"])))
            for dog, hdr in _PARENTS.items():
                acc = db.execute("SELECT g.account_id AS id FROM guardian_dogs g JOIN dogs d ON d.id=g.dog_id WHERE d.name=?", (dog,)).fetchone()
                hdr.clear(); hdr.update(bearer(auth.create_session(db, acc["id"])))
            db.commit()
        finally:
            db.close()
        yield c

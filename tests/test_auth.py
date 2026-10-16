import re

from backend import auth
from backend.database import connect
from .conftest import ADMIN, AFTERNOON, DEMO_PASSWORD, MORNING, OTHER_ORG, PARENT_BORI, PARENT_MOCHA, bearer

JIWOO = "jiwoo.han@pawcare.demo"
GOOD = "새비밀번호-2026"


def login(client, email=JIWOO, password=DEMO_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def sql(query, *args):
    db = connect()
    try:
        out = db.execute(query, args).fetchall()
        db.commit()
        return out
    finally:
        db.close()


def make_invite(client, dog_id=4, headers=MORNING):
    r = client.post("/api/invites", json={"dog_id": dog_id}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def register(client, code, email="newparent@example.com", password=GOOD, name="최하진"):
    return client.post("/api/auth/register", json={"code": code, "email": email, "password": password, "name": name})


# ---------------- 로그인 · 세션 ----------------
def test_login_sets_httponly_cookie_and_me(client):
    r = login(client, " Jiwoo.Han@PawCare.demo ")            # 대소문자·공백 무시
    assert r.status_code == 200
    acc = r.json()["account"]
    assert acc["role"] == "staff" and acc["staff"]["id"] == 1 and acc["org_name"]
    assert "password" not in r.text and "scrypt" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie and "secure" not in cookie
    assert client.get("/api/auth/me").json()["account"]["email"] == JIWOO      # 쿠키만으로 인증
    assert client.get("/api/dashboard").status_code == 200


def test_cookie_secure_flag_when_enabled(client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    assert "secure" in login(client).headers["set-cookie"].lower()


def test_csrf_header_required_for_cookie_writes(client):
    login(client)
    body = {"dog_id": 1, "title": "csrf 확인"}
    assert client.post("/api/tasks", json=body).status_code == 403                                # 쿠키 + 헤더 없음
    assert client.post("/api/tasks", json=body, headers={"X-PawCare": "1"}).status_code == 201     # 앱의 요청
    assert client.get("/api/tasks").status_code == 200                                            # 조회는 헤더 불필요


def test_wrong_password_and_unknown_email_look_identical(client):
    a = login(client, password="틀린비밀번호")
    b = login(client, email="nobody@pawcare.demo", password="아무거나")
    assert a.status_code == b.status_code == 401 and a.json()["detail"] == b.json()["detail"]
    assert "set-cookie" not in a.headers and "set-cookie" not in b.headers


def test_lockout_after_repeated_failures_and_recovery(client):
    for _ in range(5):
        assert login(client, password="x" * 9).status_code == 401
    blocked = login(client, password="x" * 9)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1 and "분 후" in blocked.json()["detail"]
    assert login(client).status_code == 429                                    # 잠긴 동안은 올바른 비밀번호도 거부
    assert login(client, email="minjae.seo@pawcare.demo").status_code == 200   # 다른 계정은 영향 없음
    sql("UPDATE login_attempts SET at='2000-01-01T00:00:00'")                   # 제한 시간이 지난 것으로 만들기
    assert login(client).status_code == 200
    assert sql("SELECT COUNT(*) FROM login_attempts WHERE key LIKE 'login:%'")[0][0] == 0   # 성공하면 실패 기록 초기화


def test_logout_invalidates_server_side_session(client):
    login(client)
    token = client.cookies.get("pawcare_session")
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 200
    assert client.post("/api/auth/logout", headers={"X-PawCare": "1"}).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(token)).json() == {"account": None}    # 토큰을 알아도 서버에서 이미 폐기됨
    assert client.get("/api/auth/me").json() == {"account": None}
    assert client.get("/api/dashboard", headers=bearer(token)).status_code == 401


def test_expired_session_rejected(client):
    sql("UPDATE sessions SET expires_at='2000-01-01T00:00:00'")
    assert client.get("/api/dashboard", headers=MORNING).status_code == 401
    assert client.get("/api/auth/me", headers=MORNING).json() == {"account": None}


def test_secrets_are_not_stored_in_plain_text(client):
    login(client)
    token = client.cookies.get("pawcare_session")
    hashes = [r[0] for r in sql("SELECT password_hash FROM accounts")]
    assert all(h.startswith("scrypt$") and DEMO_PASSWORD not in h for h in hashes)
    assert token not in str(sql("SELECT * FROM sessions"))                         # 세션 토큰도 해시만 저장
    code = make_invite(client, headers=MORNING)["code"]
    assert code.replace("-", "") not in str(sql("SELECT * FROM invites"))          # 초대 코드도 해시만 저장


def test_password_hashing_and_policy():
    h1, h2 = auth.hash_password("같은비밀번호123"), auth.hash_password("같은비밀번호123")
    assert h1 != h2 and auth.verify_password("같은비밀번호123", h1) and not auth.verify_password("다른비밀번호123", h1)
    assert not auth.verify_password("x", "garbage") and not auth.verify_password("x", "")      # 잘못된 형식은 거부(예외 없음)
    assert auth.check_password_policy("짧음") and auth.check_password_policy("password") and auth.check_password_policy("aaaaaaaaaa")
    assert auth.check_password_policy("a@b.com", "a@b.com") and auth.check_password_policy("x" * 129)
    assert auth.check_password_policy("충분히-긴-비밀번호", "a@b.com") is None


# ---------------- 역할 분리 ----------------
def test_roles_are_separated(client):
    assert client.get("/api/dogs", headers=PARENT_BORI).status_code == 403            # 보호자는 직원 API 불가
    assert client.post("/api/invites", json={"dog_id": 1}, headers=PARENT_BORI).status_code == 403
    assert client.get("/api/parent/dogs", headers=MORNING).status_code == 403         # 직원은 보호자 API 불가
    assert client.get("/api/parent/dogs").status_code == 401
    assert client.get("/api/dashboard").status_code == 401 and client.get("/api/staff").status_code == 401


def test_parent_sees_only_own_dog(client):
    assert [d["name"] for d in client.get("/api/parent/dogs", headers=PARENT_BORI).json()] == ["보리"]
    assert client.get("/api/parent/dogs/1/preview", headers=PARENT_BORI).status_code == 200
    assert client.get("/api/parent/dogs/3/preview", headers=PARENT_BORI).status_code == 404     # 다른 집 아이
    assert client.get("/api/parent/dogs/999/preview", headers=PARENT_BORI).status_code == 404    # 없는 아이와 구분되지 않음
    assert client.get("/api/parent/dogs/3/preview", headers=PARENT_MOCHA).status_code == 200


# ---------------- 초대 코드 · 보호자 가입 ----------------
def test_invite_to_register_flow(client):
    inv = make_invite(client, dog_id=4)                      # 밤이(보호자 계정 없음)
    assert re.fullmatch(r"[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}", inv["code"]) and inv["dog_name"] == "밤이"
    g = client.get("/api/dogs/4/guardians", headers=MORNING).json()
    assert g["guardians"] == [] and g["invites"][0]["status"] == "active" and inv["code"] not in str(g)
    r = register(client, inv["code"].lower().replace("-", " "))                 # 소문자·공백도 허용
    assert r.status_code == 201
    acc = r.json()["account"]
    assert acc["role"] == "parent" and [d["name"] for d in acc["dogs"]] == ["밤이"] and "httponly" in r.headers["set-cookie"].lower()
    assert [d["name"] for d in client.get("/api/parent/dogs").json()] == ["밤이"]       # 가입과 동시에 로그인
    assert client.get("/api/parent/dogs/1/preview").status_code == 404
    assert client.get("/api/dogs").status_code == 403
    g = client.get("/api/dogs/4/guardians", headers=MORNING).json()
    assert g["guardians"][0]["name"] == "최하진" and g["guardians"][0]["email"] == "n***@example.com" and g["invites"][0]["status"] == "used"
    again = register(client, inv["code"], email="other@example.com")                  # 1회용
    assert again.status_code == 400 and again.json()["errors"][0]["field"] == "code"
    assert login(client, "newparent@example.com", GOOD).status_code == 200            # 이후 비밀번호 로그인


def test_register_validation_does_not_burn_the_code(client):
    code = make_invite(client)["code"]
    bad = lambda **kw: register(client, code, **{"email": "p@example.com", **kw})
    r = bad(email="not-an-email"); assert r.status_code == 422 and r.json()["errors"][0]["field"] == "email"
    r = bad(password="short"); assert r.status_code == 422 and r.json()["errors"][0]["field"] == "password"
    r = bad(password="password"); assert r.status_code == 422
    r = bad(name="   "); assert r.status_code == 422 and r.json()["errors"][0]["field"] == "name"
    r = bad(email=JIWOO); assert r.status_code == 409 and r.json()["errors"][0]["field"] == "email"   # 이미 가입된 이메일
    assert sql("SELECT used_at FROM invites")[0][0] is None                                           # 실패하면 코드는 그대로
    assert bad().status_code == 201


def test_invite_expired_revoked_and_foreign(client):
    inv = make_invite(client)
    sql("UPDATE invites SET expires_at='2000-01-01T00:00:00' WHERE id=?", inv["id"])
    assert register(client, inv["code"]).status_code == 400
    assert client.get("/api/dogs/4/guardians", headers=MORNING).json()["invites"][0]["status"] == "expired"
    inv2 = make_invite(client)
    assert client.delete(f"/api/invites/{inv2['id']}", headers=OTHER_ORG).status_code == 404       # 다른 유치원은 취소 불가
    assert client.delete(f"/api/invites/{inv2['id']}", headers=AFTERNOON).status_code == 200
    assert register(client, inv2["code"]).status_code == 400
    inv3 = make_invite(client)
    assert register(client, inv3["code"]).status_code == 201
    assert client.delete(f"/api/invites/{inv3['id']}", headers=MORNING).status_code == 409           # 사용된 코드는 취소 불가
    assert client.post("/api/invites", json={"dog_id": 1}, headers=OTHER_ORG).status_code == 404    # 다른 유치원 반려견
    assert client.post("/api/invites", json={"dog_id": 999}, headers=MORNING).status_code == 404
    assert client.get("/api/dogs/1/guardians", headers=OTHER_ORG).status_code == 404


def test_invite_code_guessing_is_throttled(client):
    good = make_invite(client)["code"]
    for _ in range(10):
        assert register(client, "AAAA-BBBB").status_code == 400
    blocked = register(client, "AAAA-BBBB")
    assert blocked.status_code == 429 and "retry-after" in blocked.headers
    assert register(client, good).status_code == 429          # 제한 중에는 올바른 코드도 거부


# ---------------- 데모 모드 ----------------
def test_demo_features_are_off_by_default(client):
    assert client.get("/api/auth/config").json() == {"demo_mode": False}
    assert client.get("/api/auth/demo-accounts").status_code == 404
    assert client.post("/api/auth/demo-login", json={"account_id": 1}).status_code == 404
    assert client.post("/api/demo/reset").status_code == 404
    assert client.get("/api/health").json()["demo_mode"] is False


def test_demo_mode_login_only_for_demo_accounts(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    assert client.get("/api/auth/config").json() == {"demo_mode": True}
    accounts = client.get("/api/auth/demo-accounts").json()
    assert [a["name"] for a in accounts] == ["한지우", "서민재", "정하은", "김서연", "박도윤", "이수아", "오하준"]
    assert "password" not in str(accounts) and "email" not in str(accounts)
    minjae = next(a for a in accounts if a["name"] == "서민재")
    r = client.post("/api/auth/demo-login", json={"account_id": minjae["id"]})
    assert r.status_code == 200 and client.get("/api/auth/me").json()["account"]["staff"]["role"] == "오후 담당자"
    real = register(client, make_invite(client)["code"]).json()["account"]                  # 실제 가입 계정은 데모 로그인 불가
    assert client.post("/api/auth/demo-login", json={"account_id": real["id"]}).status_code == 404


# ---------------- 구형 DB 마이그레이션 ----------------
def test_migration_creates_demo_accounts_for_old_db(tmp_path):
    import sqlite3
    from backend import database
    c = sqlite3.connect(tmp_path / "old.db"); c.row_factory = sqlite3.Row
    c.executescript(database.SCHEMA)
    for t in ("sessions", "invites", "guardian_dogs", "login_attempts", "accounts"):     # 인증이 없던 시절의 DB
        c.execute(f"DROP TABLE {t}")
    c.execute("INSERT INTO organizations(name) VALUES ('x')")
    c.execute("INSERT INTO staff(org_id,name,role) VALUES (1,'한지우','오전 담당자'),(1,'새직원','관리자')")
    c.execute("INSERT INTO dogs(org_id,name,breed,birth_date,owner_name) VALUES (1,'보리','푸들','2022-04-10','김서연'),(1,'새친구','믹스','2022-04-10','누군가')")
    c.commit()
    database.init_db(c); database.init_db(c)                                            # 두 번 실행해도 중복 없음
    rows = {r["email"]: r["role"] for r in c.execute("SELECT email, role FROM accounts")}
    assert rows == {"jiwoo.han@pawcare.demo": "staff", "staff2@pawcare.demo": "staff", "seoyeon.kim@pawcare.demo": "parent"}
    assert c.execute("SELECT COUNT(*) FROM guardian_dogs").fetchone()[0] == 1

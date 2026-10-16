import base64
import os
from datetime import datetime

from backend.database import KST
from .conftest import ADMIN, AFTERNOON, MORNING, OTHER_ORG, PARENT_BORI, PARENT_TOFU

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
NEW = {"name": "초코", "breed": "닥스훈트", "birth_date": "2023-05-01", "owner_name": "강민지"}
TODAY = datetime.now(KST).date().isoformat()


def upload(client, dog_id, data=PNG, ctype="image/png", headers=MORNING):
    return client.post(f"/api/dogs/{dog_id}/photo", content=data, headers={**headers, "Content-Type": ctype})


# ---------- 반려견 등록 ----------
def test_create_dog(client):
    r = client.post("/api/dogs", json={**NEW, "care_context": {"meal": "습식 사료"}}, headers=MORNING)
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "초코" and d["photo"] is None and d["attending"] is True and d["care_context"]["meal"] == "습식 사료"
    assert d["care_context"]["other"] == ""
    names = [x["name"] for x in client.get("/api/dogs", headers=AFTERNOON).json()]   # 같은 유치원 직원에게 보임
    assert names[-1] == "초코"
    assert "초코" not in [x["name"] for x in client.get("/api/dogs", headers=OTHER_ORG).json()]
    assert client.get(f"/api/dogs/{d['id']}", headers=OTHER_ORG).status_code == 404


def test_create_dog_validation(client):
    post = lambda **kw: client.post("/api/dogs", json={**NEW, **kw}, headers=MORNING)
    assert post(name="  ").status_code == 422
    assert post(name="가" * 21).status_code == 422
    assert post(birth_date="2999-01-01").status_code == 422
    assert post(birth_date="2023/05/01").status_code == 422
    assert post(care_context={"hack": "x"}).status_code == 422
    assert client.post("/api/dogs", json={"name": "a"}, headers=MORNING).status_code == 422
    assert post().status_code == 201
    r = post()   # 같은 이름 + 같은 보호자
    assert r.status_code == 409 and "이미 등록" in r.json()["detail"]
    assert post(owner_name="다른보호자").status_code == 201   # 이름만 같고 보호자가 다르면 허용


# ---------- 사진 ----------
def test_photo_upload_serve_replace_delete(client, tmp_path):
    did = client.post("/api/dogs", json=NEW, headers=MORNING).json()["id"]
    d = upload(client, did).json()
    assert d["photo"].startswith("uploads/dogs/") and d["photo"].endswith(".png")
    served = client.get("/" + d["photo"], headers=MORNING)
    assert served.status_code == 200 and served.content == PNG and served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"
    old = tmp_path / "uploads" / "dogs" / d["photo"].rsplit("/", 1)[1]
    assert old.exists()
    d2 = upload(client, did).json()   # 교체하면 이전 파일은 삭제
    assert d2["photo"] != d["photo"] and not old.exists()
    assert client.get("/" + d2["photo"], headers=AFTERNOON).status_code == 200
    r = client.delete(f"/api/dogs/{did}/photo", headers=MORNING).json()
    assert r["photo"] is None and not any((tmp_path / "uploads" / "dogs").iterdir())
    assert client.get("/" + d2["photo"], headers=MORNING).status_code == 404


def test_photo_rejects_bad_files(client):
    did = client.post("/api/dogs", json=NEW, headers=MORNING).json()["id"]
    assert upload(client, did, ctype="text/plain").status_code == 415
    assert upload(client, did, ctype="image/svg+xml", data=b"<svg onload=alert(1)>").status_code == 415
    assert upload(client, did, data=b"<html>not an image</html>", ctype="image/png").status_code == 415   # 형식 위조
    assert upload(client, did, data=PNG, ctype="image/jpeg").status_code == 415                            # 선언과 실제가 다름
    big = PNG + b"\0" * 1_000_001
    assert upload(client, did, data=big).status_code == 413
    assert client.get(f"/api/dogs/{did}", headers=MORNING).json()["photo"] is None   # 실패 시 아무것도 저장되지 않음


def test_photo_org_isolation_and_path_safety(client):
    did = client.post("/api/dogs", json=NEW, headers=MORNING).json()["id"]
    assert upload(client, did, headers=OTHER_ORG).status_code == 404
    assert client.delete(f"/api/dogs/{did}/photo", headers=OTHER_ORG).status_code == 404
    assert client.post(f"/api/dogs/{did}/photo", content=PNG, headers={"Content-Type": "image/png"}).status_code == 401
    for bad in ("..%2f..%2fetc%2fpasswd", "a.txt", "x.svg", ".env", "%2e%2e%2fsecret.png"):
        assert client.get(f"/uploads/dogs/{bad}", headers=MORNING).status_code == 404, bad


# ---------- 일과 ----------
def test_routine_blocks_and_counts(client):
    r = client.get("/api/routine", headers=MORNING).json()
    names = [b["name"] for b in r["blocks"]]
    assert names == ["등원·컨디션 체크", "오전 교육·놀이", "점심·휴식", "오후 산책·놀이", "그루밍·정리", "하원 준비"]
    by = {b["name"]: b for b in r["blocks"]}
    assert by["점심·휴식"]["record_count"] == 3 and by["점심·휴식"]["dog_count"] == 2     # 보리 2건 + 밤이 1건
    assert by["오전 교육·놀이"]["dog_count"] == 2 and by["오후 산책·놀이"]["dog_count"] == 1   # 두부·모카 / 콩이
    assert r["program"]["title"] and r["default_block_id"] in {b["id"] for b in r["blocks"]}
    assert all(b["dogs_total"] == 5 for b in r["blocks"])


def test_routine_block_detail_and_handoff(client):
    blocks = {b["name"]: b["id"] for b in client.get("/api/routine", headers=MORNING).json()["blocks"]}
    lunch = client.get(f"/api/routine/{blocks['점심·휴식']}", headers=MORNING).json()
    assert lunch["handoff"] is None and lunch["with_record"] == 2 and len(lunch["dogs"]) == 5
    bori = next(d for d in lunch["dogs"] if d["name"] == "보리")
    assert len(bori["records"]) == 2
    no_rec = [d["name"] for d in lunch["dogs"] if not d["records"]]
    assert set(no_rec) == {"두부", "모카", "콩이"}   # 이 구간에 기록이 없는 아이들
    pm = client.get(f"/api/routine/{blocks['오후 산책·놀이']}", headers=AFTERNOON).json()
    h = pm["handoff"]
    assert h["label"] == "오전 → 오후 담당자" and h["at"] == "13:00"
    assert h["counts"] == {"pending": 1, "todo": 1, "in_progress": 1}      # 샘플 업무 3건(완료 1건 제외)
    assert [t["id"] for t in h["tasks"]] == [1, 2, 3]
    assert client.get(f"/api/routine/{blocks['점심·휴식']}", headers=OTHER_ORG).status_code == 404   # 다른 유치원 구간


def test_record_gets_block_from_time_and_can_override(client):
    blocks = {b["name"]: b["id"] for b in client.get("/api/routine", headers=MORNING).json()["blocks"]}
    mk = lambda **kw: client.post("/api/records", headers=MORNING, json={"dog_id": 2, "record_type": "식사", "content": "x", **kw})
    r = mk(observed_at=f"{TODAY}T12:30")
    assert r.status_code == 201 and r.json()["block_name"] == "점심·휴식"
    assert mk(observed_at=f"{TODAY}T14:10").json()["block_name"] == "오후 산책·놀이"
    assert mk(observed_at=f"{TODAY}T23:00").json()["block_id"] is None          # 영업시간 밖
    assert mk(observed_at=f"{TODAY}T12:30", block_id=blocks["그루밍·정리"]).json()["block_name"] == "그루밍·정리"   # 직원이 직접 선택
    assert mk(block_id=99999).status_code == 422
    other = client.get("/api/routine", headers=OTHER_ORG).json()["blocks"][0]["id"]
    assert mk(block_id=other).status_code == 422                                  # 다른 유치원 구간 사용 불가


def test_migration_adds_routine_to_old_db(tmp_path):
    import sqlite3
    from backend import database
    old = database.SCHEMA.replace(",\n    block_id INTEGER REFERENCES routine_blocks(id)", "")
    old = old[:old.index("CREATE TABLE IF NOT EXISTS routine_blocks")] + old[old.index("CREATE TABLE IF NOT EXISTS dogs"):]
    c = sqlite3.connect(tmp_path / "old.db"); c.row_factory = sqlite3.Row
    c.executescript(old)
    assert "routine_blocks" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    c.execute("INSERT INTO organizations(name) VALUES ('x')")
    c.execute("INSERT INTO staff(org_id,name,role) VALUES (1,'a','관리자')")
    c.execute("INSERT INTO dogs(org_id,name,breed,birth_date,owner_name) VALUES (1,'보리','푸들','2022-04-10','a')")
    c.execute("INSERT INTO care_records(org_id,dog_id,author_id,record_type,content,observed_at,created_at) VALUES (1,1,1,'식사','x','2026-01-01T12:30:00','2026-01-01T12:30:00')")
    c.commit()
    database.init_db(c); database.init_db(c)   # 두 번 실행해도 안전
    assert c.execute("SELECT COUNT(*) FROM routine_blocks").fetchone()[0] == 6
    assert c.execute("SELECT b.name FROM care_records r JOIN routine_blocks b ON b.id=r.block_id").fetchone()[0] == "점심·휴식"


def test_profile_photo_requires_login_and_matching_org_or_guardian(client):
    d = upload(client, 1).json()                                            # 보리(유치원 1) 프로필 사진
    url = "/" + d["photo"]
    assert client.get(url).status_code == 401                                # 로그인하지 않으면 주소를 알아도 열 수 없음
    assert client.get(url, headers=AFTERNOON).status_code == 200            # 같은 유치원 직원
    assert client.get(url, headers=OTHER_ORG).status_code == 404            # 다른 유치원 직원: 존재 여부도 알 수 없음
    assert client.get(url, headers=PARENT_BORI).status_code == 200          # 보리의 보호자
    assert client.get(url, headers=PARENT_TOFU).status_code == 404          # 다른 집 보호자
    assert client.get(url, headers=MORNING).headers["cache-control"].startswith("private")

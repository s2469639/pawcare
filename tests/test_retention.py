"""M6: 퇴원 처리와 3개월 뒤 자료 삭제 — 사진·영상 파일과 보호자 연결만 삭제하고, 글 기록과 업무 이력은 유지한다."""
from datetime import datetime

from backend.database import add_months, connect
from .conftest import ADMIN, MORNING, OTHER_ORG, PARENT_BORI, PARENT_TOFU
from .test_auth import make_invite, sql
from .test_dogs_routine import upload as upload_profile
from .test_media import png, up
from .test_sharing import approve

TOFU, MOCHA = 2, 3


def discharge(client, dog=TOFU, headers=ADMIN):
    return client.post(f"/api/dogs/{dog}/discharge", headers=headers)


def make_due(dog=TOFU):
    sql("UPDATE dogs SET purge_after='2000-01-01T00:00:00' WHERE id=?", dog)


def files(tmp_path, sub):
    d = tmp_path / "uploads" / sub
    return sorted(p.name for p in d.rglob("*") if p.is_file()) if d.exists() else []


def test_add_months_handles_month_ends_and_leap_years():
    f = lambda y, m, d, n=3: add_months(datetime(y, m, d, 9, 30), n).isoformat()
    assert f(2026, 11, 30) == "2027-02-28T09:30:00"
    assert f(2027, 11, 30) == "2028-02-29T09:30:00"
    assert f(2026, 10, 31) == "2027-01-31T09:30:00"
    assert f(2026, 12, 15) == "2027-03-15T09:30:00"


def test_discharge_is_admin_only_and_sets_three_month_schedule(client):
    assert discharge(client, headers=MORNING).status_code == 403
    assert discharge(client, headers=PARENT_TOFU).status_code == 403
    assert discharge(client, headers=OTHER_ORG).status_code == 404
    assert client.post(f"/api/dogs/{TOFU}/discharge").status_code == 401
    d = discharge(client).json()
    assert d["discharged"] and d["attending"] is False and d["purged_at"] is None
    assert datetime.fromisoformat(d["purge_after"]) == add_months(datetime.fromisoformat(d["discharged_at"]), 3)
    assert 88 <= d["purge_days_left"] <= 93
    assert discharge(client).status_code == 409                                            # 이미 퇴원 처리됨


def test_discharged_dog_is_hidden_and_cannot_get_new_things(client):
    mid = up(client, png(), record=3, dogs="2").json()["id"]                               # 두부의 기록에 사진 첨부(퇴원 전)
    discharge(client)
    assert "두부" not in [d["name"] for d in client.get("/api/dogs", headers=MORNING).json()]
    assert [d["name"] for d in client.get("/api/dogs?status=discharged", headers=MORNING).json()] == ["두부"]
    assert client.get("/api/dashboard", headers=MORNING).json()["attending_dogs"] == 4
    blocks = {b["name"]: b["id"] for b in client.get("/api/routine", headers=MORNING).json()["blocks"]}
    names = [d["name"] for d in client.get(f"/api/routine/{blocks['점심·휴식']}", headers=MORNING).json()["dogs"]]
    assert "두부" not in names
    # 새 기록·사진·업무·태그·공개는 막힌다
    assert client.post("/api/records", headers=MORNING, json={"dog_id": TOFU, "record_type": "식사", "content": "x"}).status_code == 409
    assert up(client, png(), record=3, dogs="2").status_code == 409                          # 퇴원한 아이의 기록에 새 사진
    assert up(client, png(), record=2, dogs="1,2").status_code == 409                        # 다른 기록이라도 퇴원한 아이를 새로 태그할 수 없음
    assert client.post("/api/tasks", headers=MORNING, json={"dog_id": TOFU, "title": "x"}).status_code == 409
    assert approve(client, record=3, text="새 공개", media=[{"media_id": mid, "dog_ids": [2]}]).status_code == 409
    assert client.get(f"/api/dogs/{TOFU}", headers=MORNING).status_code == 200                 # 프로필·기존 기록은 볼 수 있다


def test_existing_shares_stay_visible_to_parent_until_purge(client):
    mid = up(client, png(), record=3, dogs="2").json()["id"]
    assert approve(client, record=3, text="공개된 내용", media=[{"media_id": mid, "dog_ids": [2]}]).status_code == 200
    d = discharge(client).json()
    dogs = client.get("/api/parent/dogs", headers=PARENT_TOFU).json()
    assert dogs[0]["purge_after"] == d["purge_after"] and dogs[0]["discharged_at"]            # 보호자 화면에 삭제 예정일 안내
    assert client.get(f"/api/parent/dogs/{TOFU}/preview", headers=PARENT_TOFU).json()["records"][0]["media"][0]["id"] == mid
    assert client.get(f"/api/parent/media/{mid}/file", headers=PARENT_TOFU).status_code == 200
    r = client.patch("/api/records/3/parent-approval", json={"action": "revoke"}, headers=MORNING)   # 공개 취소는 퇴원 후에도 가능
    assert r.status_code == 200 and client.get(f"/api/parent/media/{mid}/file", headers=PARENT_TOFU).status_code == 404


def test_readmit(client):
    assert client.post(f"/api/dogs/{TOFU}/readmit", headers=ADMIN).status_code == 409        # 퇴원 상태가 아님
    discharge(client)
    assert client.post(f"/api/dogs/{TOFU}/readmit", headers=MORNING).status_code == 403
    assert client.post(f"/api/dogs/{TOFU}/readmit", headers=OTHER_ORG).status_code == 404
    d = client.post(f"/api/dogs/{TOFU}/readmit", headers=ADMIN).json()
    assert d["attending"] is True and d["discharged_at"] is None and d["purge_after"] is None
    assert client.post("/api/records", headers=MORNING, json={"dog_id": TOFU, "record_type": "식사", "content": "복귀"}).status_code == 201
    assert "두부" in [x["name"] for x in client.get("/api/dogs", headers=MORNING).json()]


def test_purge_deletes_photos_and_guardian_links_but_keeps_text_and_tasks(client, tmp_path):
    only = up(client, png(), record=3, dogs="2").json()["id"]                               # 두부만 찍힌 사진 → 삭제
    group = up(client, png(40, 40), record=2, dogs="1,2").json()["id"]                       # 보리·두부 단체 사진 → 보리를 위해 보존
    approve(client, record=2, text="보리 기록", media=[{"media_id": group, "dog_ids": [1, 2]}])
    approve(client, record=3, text="두부 기록", media=[{"media_id": only, "dog_ids": [2]}])
    upload_profile(client, TOFU)                                                             # 직접 올린 프로필 사진
    make_invite(client, dog_id=TOFU)                                                          # 쓰지 않은 초대 코드
    client.post(f"/api/parent/dogs/{TOFU}/seen", headers=PARENT_TOFU)
    assert len(files(tmp_path, "media")) == 4 and len(files(tmp_path, "dogs")) == 1
    discharge(client)
    # 삭제 예정일 전에는 아무것도 지워지지 않는다
    assert client.post("/api/retention/purge", headers=ADMIN).json()["count"] == 0
    assert client.get(f"/api/parent/media/{only}/file", headers=PARENT_TOFU).status_code == 200
    make_due()
    due = client.get("/api/retention/discharged", headers=ADMIN).json()
    assert [(x["name"], x["due"]) for x in due] == [("두부", True)]
    assert client.post("/api/retention/purge", headers=MORNING).status_code == 403          # 관리자만
    assert client.post("/api/retention/purge", headers=PARENT_TOFU).status_code == 403
    assert client.post("/api/retention/purge", headers=OTHER_ORG).json()["count"] == 0       # 다른 유치원 관리자는 우리 자료에 영향 없음
    assert client.get(f"/api/parent/media/{only}/file", headers=PARENT_TOFU).status_code == 200
    res = client.post("/api/retention/purge", headers=ADMIN).json()
    assert res["count"] == 1
    r = res["purged"][0]
    assert (r["photos_deleted"], r["group_photos_kept"], r["profile_photo_deleted"], r["guardian_links_deleted"]) == (1, 1, True, 1)
    # 파일: 두부만 찍힌 사진과 프로필 사진은 사라지고, 단체 사진(보리)만 남는다
    assert len(files(tmp_path, "media")) == 2 and files(tmp_path, "dogs") == []
    # 보호자: 연결이 끊겨 아무것도 볼 수 없다. 보리의 보호자는 단체 사진을 계속 본다
    assert client.get("/api/parent/dogs", headers=PARENT_TOFU).json() == []
    assert client.get(f"/api/parent/dogs/{TOFU}/preview", headers=PARENT_TOFU).status_code == 404
    assert client.get(f"/api/parent/media/{group}/file", headers=PARENT_TOFU).status_code == 404
    assert client.get(f"/api/parent/media/{group}/file", headers=PARENT_BORI).status_code == 200
    assert client.get(f"/api/media/{only}/file", headers=MORNING).status_code == 404
    # DB 흔적
    assert sql("SELECT COUNT(*) FROM guardian_dogs WHERE dog_id=?", TOFU)[0][0] == 0
    assert sql("SELECT COUNT(*) FROM invites WHERE dog_id=?", TOFU)[0][0] == 0
    assert sql("SELECT COUNT(*) FROM parent_reads WHERE dog_id=?", TOFU)[0][0] == 0
    assert sql("SELECT COUNT(*) FROM media_dogs WHERE dog_id=?", TOFU)[0][0] == 0 and sql("SELECT COUNT(*) FROM media_shares WHERE dog_id=?", TOFU)[0][0] == 0
    assert sql("SELECT COUNT(*) FROM media")[0][0] == 1 and sql("SELECT photo, purged_at FROM dogs WHERE id=?", TOFU)[0][0] is None
    # 글 기록과 업무 이력은 그대로
    assert [x["content"] for x in client.get(f"/api/dogs/{TOFU}/records?scope=all", headers=MORNING).json()] == ["산책 후 물을 마셨습니다."]
    assert any(t["dog_id"] == TOFU for t in client.get("/api/tasks", headers=MORNING).json())
    # 되돌릴 수 없다 · 중복 실행은 아무 일도 하지 않는다
    assert client.post(f"/api/dogs/{TOFU}/readmit", headers=ADMIN).status_code == 409
    assert discharge(client).status_code == 409
    assert client.post("/api/retention/purge", headers=ADMIN).json()["count"] == 0
    assert client.get("/api/retention/discharged", headers=ADMIN).json()[0]["purged_at"]


def test_purge_only_touches_due_dogs(client):
    discharge(client, dog=MOCHA)                                                          # 삭제 예정일이 아직 먼 아이
    discharge(client, dog=TOFU)
    make_due(TOFU)
    assert client.post("/api/retention/purge", headers=ADMIN).json()["count"] == 1
    assert sql("SELECT COUNT(*) FROM guardian_dogs WHERE dog_id=?", MOCHA)[0][0] == 1       # 모카의 보호자 연결은 그대로
    assert sql("SELECT COUNT(*) FROM guardian_dogs WHERE dog_id=?", TOFU)[0][0] == 0


def test_startup_purge_covers_every_organization(client):
    from backend import retention
    discharge(client, dog=TOFU); make_due(TOFU)
    assert client.post("/api/dogs/6/discharge", headers=OTHER_ORG).status_code == 200      # 다른 유치원(관리자 오하준)
    make_due(6)
    db = connect()
    try:
        done = retention.purge_due(db)                                                       # 서버 시작 시 점검과 같은 함수
    finally:
        db.close()
    assert sorted(d["name"] for d in done) == ["구름", "두부"]


def test_migration_adds_retention_columns(tmp_path):
    import sqlite3
    from backend import database
    old = database.SCHEMA.replace(",\n    discharged_at TEXT,\n    purge_after TEXT,\n    purged_at TEXT", "")
    c = sqlite3.connect(tmp_path / "old.db"); c.row_factory = sqlite3.Row
    c.executescript(old)
    assert "purged_at" not in {r["name"] for r in c.execute("PRAGMA table_info(dogs)")}
    database.init_db(c); database.init_db(c)
    assert {"discharged_at", "purge_after", "purged_at"} <= {r["name"] for r in c.execute("PRAGMA table_info(dogs)")}

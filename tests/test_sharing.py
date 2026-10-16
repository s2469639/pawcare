"""M3: 공개 승인. 보호자에게는 '직원이 고른 사진'만, '해당 아이'에게만 보여야 한다."""
import json

from .conftest import ADMIN, AFTERNOON, MORNING, OTHER_ORG, PARENT_BORI, PARENT_MOCHA, PARENT_TOFU
from .test_media import png, up

REC = 2        # 보리의 기록(샘플)


def approve(client, record=REC, text="오늘도 잘 지냈어요.", media=None, headers=MORNING):
    body = {"action": "approve", "parent_text": text, "media": media or []}
    return client.patch(f"/api/records/{record}/parent-approval", json=body, headers=headers)


def preview(client, headers, dog=1):
    return client.get(f"/api/parent/dogs/{dog}/preview", headers=headers)


def parent_file(client, headers, mid, size="full"):
    return client.get(f"/api/parent/media/{mid}/file?size={size}", headers=headers)


def two_photos(client, dogs="1"):
    return up(client, png(), dogs=dogs).json()["id"], up(client, png(40, 40), dogs=dogs).json()["id"]


def test_nothing_is_visible_to_parents_before_approval(client):
    a, b = two_photos(client)
    assert preview(client, PARENT_BORI).json()["records"] == []
    assert parent_file(client, PARENT_BORI, a).status_code == 404            # 첨부는 됐지만 공개 전
    assert approve(client, text="글만 공개", media=[]).status_code == 200      # 글만 승인해도 사진은 공개되지 않음
    rec = preview(client, PARENT_BORI).json()["records"][0]
    assert rec["parent_text"] == "글만 공개" and rec["media"] == []
    assert parent_file(client, PARENT_BORI, a).status_code == 404 and parent_file(client, PARENT_BORI, b).status_code == 404


def test_only_selected_photos_are_shared(client):
    a, b = two_photos(client)
    assert approve(client, media=[{"media_id": a, "dog_ids": [1]}]).status_code == 200
    rec = preview(client, PARENT_BORI).json()["records"][0]
    assert [m["id"] for m in rec["media"]] == [a]                              # 선택한 사진만
    ok = parent_file(client, PARENT_BORI, a)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/webp" and ok.headers["cache-control"].startswith("private")
    assert parent_file(client, PARENT_BORI, a, "thumb").status_code == 200
    assert parent_file(client, PARENT_BORI, b).status_code == 404               # 선택하지 않은 사진
    assert parent_file(client, PARENT_TOFU, a).status_code == 404               # 다른 집 보호자
    assert parent_file(client, PARENT_MOCHA, a).status_code == 404
    assert client.get(f"/api/parent/media/{a}/file").status_code == 401
    assert client.get(f"/api/parent/media/{a}/file", headers=MORNING).status_code == 403   # 직원은 직원용 경로를 쓴다
    assert client.get(f"/api/media/{a}/file", headers=PARENT_BORI).status_code == 403      # 보호자는 직원용 경로 불가
    assert parent_file(client, PARENT_BORI, 999).status_code == 404


def test_group_photo_goes_only_to_chosen_dogs_and_never_leaks_caption(client):
    mid = up(client, png(), dogs="1,2").json()["id"]                            # 보리 기록에 첨부, 보리·두부가 함께 찍힘
    approve(client, text="보리는 점심을 적게 먹었어요(비공개 내용)", media=[{"media_id": mid, "dog_ids": [1]}])
    tofu = preview(client, PARENT_TOFU, dog=2).json()
    assert tofu["records"] == [] and tofu["group_photos"] == []                 # 기본: 승인한 기록의 아이 보호자에게만
    assert parent_file(client, PARENT_TOFU, mid).status_code == 404
    approve(client, text="보리는 점심을 적게 먹었어요(비공개 내용)", media=[{"media_id": mid, "dog_ids": [1, 2]}])    # 직원이 추가 선택
    tofu = preview(client, PARENT_TOFU, dog=2).json()
    assert [p["id"] for p in tofu["group_photos"]] == [mid] and tofu["records"] == []
    assert "점심" not in json.dumps(tofu, ensure_ascii=False) and "비공개" not in json.dumps(tofu, ensure_ascii=False)   # 보리의 글은 새지 않음
    assert parent_file(client, PARENT_TOFU, mid).status_code == 200
    assert preview(client, PARENT_BORI).json()["records"][0]["media"][0]["id"] == mid
    assert parent_file(client, PARENT_MOCHA, mid).status_code == 404            # 태그되지 않은 아이의 보호자


def test_revoke_and_reapprove_replace_shares(client):
    a, b = two_photos(client)
    approve(client, media=[{"media_id": a, "dog_ids": [1]}])
    approve(client, media=[{"media_id": b, "dog_ids": [1]}])                    # 다시 승인하면 이전 선택은 사라진다
    assert [m["id"] for m in preview(client, PARENT_BORI).json()["records"][0]["media"]] == [b]
    assert parent_file(client, PARENT_BORI, a).status_code == 404
    r = client.patch(f"/api/records/{REC}/parent-approval", json={"action": "revoke"}, headers=AFTERNOON)
    assert r.status_code == 200 and all(m["shared_dog_ids"] == [] for m in r.json()["media"])
    assert preview(client, PARENT_BORI).json()["records"] == [] and parent_file(client, PARENT_BORI, b).status_code == 404   # 즉시 사라짐
    from backend.database import connect
    db = connect(); n = db.execute("SELECT COUNT(*) FROM media_shares").fetchone()[0]; db.close()
    assert n == 0


def test_photo_only_approval_and_validation(client):
    a, b = two_photos(client)
    assert approve(client, text="", media=[{"media_id": a, "dog_ids": [1]}]).status_code == 200      # 글 없이 사진만
    assert preview(client, PARENT_BORI).json()["records"][0]["parent_text"] == ""
    bad = approve(client, text="  ", media=[])
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "parent_text"             # 글도 사진도 없음
    assert approve(client, media=[{"media_id": a, "dog_ids": []}], text="").status_code == 422      # 사진을 골랐지만 공개 대상이 없음
    assert approve(client, media=[{"media_id": a, "dog_ids": [2]}]).status_code == 422              # 사진에 태그되지 않은 아이
    assert approve(client, media=[{"media_id": a, "dog_ids": [1]}, {"media_id": a, "dog_ids": [1]}]).status_code == 422   # 중복
    other = up(client, png(), record=1).json()["id"]                                                # 다른 기록에 첨부된 사진
    assert approve(client, media=[{"media_id": other, "dog_ids": [1]}]).status_code == 422
    assert approve(client, media=[{"media_id": 99999, "dog_ids": [1]}]).status_code == 422
    assert approve(client, headers=OTHER_ORG).status_code == 404                                    # 다른 유치원
    assert approve(client, headers=PARENT_BORI).status_code == 403
    assert approve(client, record=999).status_code == 404


def test_removing_a_tag_removes_that_dogs_access(client):
    mid = up(client, png(), dogs="1,2").json()["id"]
    approve(client, media=[{"media_id": mid, "dog_ids": [1, 2]}])
    assert parent_file(client, PARENT_TOFU, mid).status_code == 200
    r = client.patch(f"/api/media/{mid}", json={"dog_ids": [1]}, headers=ADMIN)                     # 두부가 찍히지 않았음을 정정
    assert r.json()["shared_dog_ids"] == [1]
    assert parent_file(client, PARENT_TOFU, mid).status_code == 404
    assert parent_file(client, PARENT_BORI, mid).status_code == 200


def test_deleting_a_photo_removes_access(client):
    mid = up(client, png()).json()["id"]
    approve(client, media=[{"media_id": mid, "dog_ids": [1]}])
    assert parent_file(client, PARENT_BORI, mid).status_code == 200
    client.delete(f"/api/media/{mid}", headers=MORNING)
    assert parent_file(client, PARENT_BORI, mid).status_code == 404
    assert preview(client, PARENT_BORI).json()["records"][0]["media"] == []


def test_consent_is_required_before_sharing(client):
    dog = client.post("/api/dogs", headers=MORNING, json={"name": "초코", "breed": "닥스훈트", "birth_date": "2023-05-01", "owner_name": "강민지"}).json()
    assert dog["consent_at"] is None
    rec = client.post("/api/records", headers=MORNING, json={"dog_id": dog["id"], "record_type": "활동", "content": "산책"}).json()
    mid = up(client, png(), record=rec["id"]).json()["id"]
    r = approve(client, record=rec["id"], media=[{"media_id": mid, "dog_ids": [dog["id"]]}])
    assert r.status_code == 409 and "동의" in r.json()["detail"] and "초코" in r.json()["detail"]
    assert client.get(f"/api/dogs/{dog['id']}", headers=MORNING).json()["records_today"][0]["parent_status"] == "private"   # 아무것도 공개되지 않음
    assert client.post(f"/api/dogs/{dog['id']}/consent", headers=OTHER_ORG).status_code == 404
    assert client.post(f"/api/dogs/{dog['id']}/consent", headers=PARENT_BORI).status_code == 403
    assert client.post(f"/api/dogs/{dog['id']}/consent", headers=MORNING).json()["consent_at"]
    assert approve(client, record=rec["id"], media=[{"media_id": mid, "dog_ids": [dog["id"]]}]).status_code == 200
    ok = client.post("/api/dogs", headers=MORNING, json={"name": "마루", "breed": "믹스", "birth_date": "2023-05-01", "owner_name": "한가람", "consent_confirmed": True}).json()
    assert ok["consent_at"]                                                                          # 등록할 때 동의 확인을 체크한 경우


def test_group_photo_to_dog_without_consent_is_blocked(client):
    new = client.post("/api/dogs", headers=MORNING, json={"name": "초코", "breed": "닥스훈트", "birth_date": "2023-05-01", "owner_name": "강민지"}).json()
    mid = up(client, png(), dogs=f"1,{new['id']}").json()["id"]
    r = approve(client, media=[{"media_id": mid, "dog_ids": [1, new["id"]]}])
    assert r.status_code == 409 and "초코" in r.json()["detail"]
    assert approve(client, media=[{"media_id": mid, "dog_ids": [1]}]).status_code == 200            # 동의된 아이에게만 공개하면 가능


def test_migration_adds_consent_for_sample_dogs_only(tmp_path):
    import sqlite3
    from backend import database
    old = database.SCHEMA.replace(",\n    consent_at TEXT", "")
    c = sqlite3.connect(tmp_path / "old.db"); c.row_factory = sqlite3.Row
    c.executescript(old)
    c.execute("INSERT INTO organizations(name) VALUES ('x')")
    c.execute("INSERT INTO dogs(org_id,name,breed,birth_date,owner_name) VALUES (1,'보리','푸들','2022-04-10','a'),(1,'새친구','믹스','2022-04-10','b')")
    c.commit()
    database.init_db(c); database.init_db(c)
    got = {r["name"]: r["consent_at"] for r in c.execute("SELECT name, consent_at FROM dogs")}
    assert got["보리"] and got["새친구"] is None

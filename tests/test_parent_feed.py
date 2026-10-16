"""M4: 보호자 알림장 — '새 알림장' 표시(읽음 처리)와 항목 구성."""
from .conftest import MORNING, PARENT_BORI, PARENT_MOCHA, PARENT_TOFU, bearer
from .test_auth import GOOD, make_invite, register
from .test_media import png, up
from .test_sharing import approve, preview


def dogs(client, headers):
    return {d["name"]: d for d in client.get("/api/parent/dogs", headers=headers).json()}


def new_record(client, dog_id, text="기록"):
    return client.post("/api/records", headers=MORNING, json={"dog_id": dog_id, "record_type": "활동", "content": text}).json()["id"]


def test_unseen_counts_and_mark_seen(client):
    assert dogs(client, PARENT_MOCHA)["모카"]["unseen"] == 1                       # 샘플로 이미 공개된 기록 1건
    assert dogs(client, PARENT_BORI)["보리"]["unseen"] == 0                         # 보리는 공개된 기록이 없음
    p = preview(client, PARENT_MOCHA, dog=3).json()
    assert p["records"][0]["is_new"] is True and p["previous_seen_at"] is None
    assert client.post("/api/parent/dogs/3/seen", headers=PARENT_MOCHA).json() == {"unseen": 0}
    assert dogs(client, PARENT_MOCHA)["모카"]["unseen"] == 0
    p = preview(client, PARENT_MOCHA, dog=3).json()
    assert p["records"][0]["is_new"] is False and p["previous_seen_at"]
    rid = new_record(client, 3)
    approve(client, record=rid, text="새로 공개")
    assert dogs(client, PARENT_MOCHA)["모카"]["unseen"] == 1                       # 읽은 뒤에 공개된 것만 '새 것'
    new = preview(client, PARENT_MOCHA, dog=3).json()["records"]
    assert [r["is_new"] for r in new] == [True, False] or sorted(r["is_new"] for r in new) == [False, True]


def test_private_and_revoked_do_not_count(client):
    rid = new_record(client, 1)
    assert dogs(client, PARENT_BORI)["보리"]["unseen"] == 0                          # 승인 전에는 알림장에 없음
    approve(client, record=rid, text="공개")
    assert dogs(client, PARENT_BORI)["보리"]["unseen"] == 1
    client.patch(f"/api/records/{rid}/parent-approval", json={"action": "revoke"}, headers=MORNING)
    assert dogs(client, PARENT_BORI)["보리"]["unseen"] == 0


def test_group_photos_count_once_per_record_and_are_per_dog(client):
    a = up(client, png(), dogs="1,2").json()["id"]
    b = up(client, png(30, 30), dogs="1,2").json()["id"]
    approve(client, text="보리 기록", media=[{"media_id": a, "dog_ids": [1, 2]}, {"media_id": b, "dog_ids": [1, 2]}])
    assert dogs(client, PARENT_TOFU)["두부"]["unseen"] == 1                          # 같은 기록의 사진 2장은 한 항목
    assert dogs(client, PARENT_BORI)["보리"]["unseen"] == 1
    assert dogs(client, PARENT_MOCHA)["모카"]["unseen"] == 1                        # 모카는 샘플 기록 1건만(단체 사진은 공개 대상 아님)
    client.post("/api/parent/dogs/2/seen", headers=PARENT_TOFU)
    assert dogs(client, PARENT_TOFU)["두부"]["unseen"] == 0 and dogs(client, PARENT_BORI)["보리"]["unseen"] == 1   # 아이별로 따로 관리
    g = preview(client, PARENT_TOFU, dog=2).json()["group_photos"]
    assert [x["is_new"] for x in g] == [False, False]


def test_seen_endpoint_is_scoped_to_own_dogs(client):
    assert client.post("/api/parent/dogs/1/seen", headers=PARENT_TOFU).status_code == 404     # 남의 아이
    assert client.post("/api/parent/dogs/999/seen", headers=PARENT_TOFU).status_code == 404
    assert client.post("/api/parent/dogs/1/seen", headers=MORNING).status_code == 403
    assert client.post("/api/parent/dogs/1/seen").status_code == 401


def test_new_guardian_starts_with_nothing_new(client):
    rid = new_record(client, 4)                                                     # 밤이(보호자 계정 없음)
    approve(client, record=rid, text="가입 전에 공개된 기록")
    code = make_invite(client, dog_id=4)["code"]
    reg = register(client, code)
    assert reg.status_code == 201
    token = {"Authorization": "Bearer " + client.cookies.get("pawcare_session")}
    assert dogs(client, token)["밤이"]["unseen"] == 0                                # 가입 전 내용은 '새 것'이 아니다(내용은 볼 수 있음)
    assert len(preview(client, token, dog=4).json()["records"]) == 1
    rid2 = new_record(client, 4)
    approve(client, record=rid2, text="가입 후 공개")
    assert dogs(client, token)["밤이"]["unseen"] == 1

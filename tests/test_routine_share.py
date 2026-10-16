"""M5: 일과 구간의 '사진 공유 시점' — 이 구간에서 아직 사진을 보호자에게 공개하지 않은 아이를 보여준다."""
from .conftest import MORNING, OTHER_ORG
from .test_media import png, up
from .test_sharing import approve


def blocks(client, headers=MORNING):
    return {b["name"]: b for b in client.get("/api/routine", headers=headers).json()["blocks"]}


def detail(client, name, headers=MORNING):
    bid = blocks(client, headers)[name]["id"]
    return client.get(f"/api/routine/{bid}", headers=headers).json()


def photos_of(d):
    return {x["name"]: x["photos"] for x in d["dogs"]}


def test_share_prompt_blocks_are_flagged(client):
    b = blocks(client)
    assert [n for n, x in b.items() if x["share_prompt"]] == ["점심·휴식", "하원 준비"]
    assert b["점심·휴식"]["dogs_shared"] == 0 and "dogs_shared" not in b["오전 교육·놀이"]
    assert detail(client, "오전 교육·놀이")["share"] is None                      # 사진 공유 시점이 아닌 구간에는 현황이 없다
    assert all(x["photos"] == {"shared": 0, "pending": 0} for x in detail(client, "오전 교육·놀이")["dogs"])     # 계산하지 않으므로 항상 0


def test_nobody_has_photos_at_first(client):
    d = detail(client, "점심·휴식")
    assert d["block"]["share_prompt"] is True
    assert d["share"] == {"dogs_total": 5, "dogs_shared": 0, "dogs_pending": 0, "dogs_none": 5}


def test_pending_then_shared_per_dog(client):
    mid = up(client, png(), dogs="1,2").json()["id"]                                 # 점심 구간의 보리 기록(#2)에 첨부, 보리·두부 태그
    p = photos_of(detail(client, "점심·휴식"))
    assert p["보리"] == {"shared": 0, "pending": 1} and p["두부"] == {"shared": 0, "pending": 1} and p["모카"] == {"shared": 0, "pending": 0}
    d = detail(client, "점심·휴식")
    assert d["share"] == {"dogs_total": 5, "dogs_shared": 0, "dogs_pending": 2, "dogs_none": 3}
    approve(client, media=[{"media_id": mid, "dog_ids": [1]}])                          # 보리에게만 공개
    p = photos_of(detail(client, "점심·휴식"))
    assert p["보리"] == {"shared": 1, "pending": 0} and p["두부"] == {"shared": 0, "pending": 1}      # 두부는 아직 공개 전
    assert detail(client, "점심·휴식")["share"] == {"dogs_total": 5, "dogs_shared": 1, "dogs_pending": 1, "dogs_none": 3}
    assert blocks(client)["점심·휴식"]["dogs_shared"] == 1
    approve(client, media=[{"media_id": mid, "dog_ids": [1, 2]}])                        # 두부에게도
    assert detail(client, "점심·휴식")["share"]["dogs_pending"] == 0 and blocks(client)["점심·휴식"]["dogs_shared"] == 2
    client.patch(f"/api/records/2/parent-approval", json={"action": "revoke"}, headers=MORNING)       # 취소하면 다시 '공개 전'
    assert detail(client, "점심·휴식")["share"] == {"dogs_total": 5, "dogs_shared": 0, "dogs_pending": 2, "dogs_none": 3}


def test_photos_count_in_the_block_of_their_record_only(client):
    up(client, png(), record=4, dogs="3")                                              # 모카의 기록(#4)은 오전 교육 구간
    assert photos_of(detail(client, "점심·휴식"))["모카"] == {"shared": 0, "pending": 0}
    assert detail(client, "오전 교육·놀이")["share"] is None


def test_share_status_is_org_scoped(client):
    up(client, png(), dogs="1")
    org2 = blocks(client, OTHER_ORG)
    assert org2["점심·휴식"]["dogs_shared"] == 0
    d = detail(client, "점심·휴식", OTHER_ORG)
    assert [x["name"] for x in d["dogs"]] == ["구름"] and d["share"]["dogs_total"] == 1 and d["share"]["dogs_pending"] == 0


def test_migration_adds_share_prompt_flag(tmp_path):
    import sqlite3
    from backend import database
    old = database.SCHEMA.replace(",\n    share_prompt INTEGER NOT NULL DEFAULT 0", "")
    c = sqlite3.connect(tmp_path / "old.db"); c.row_factory = sqlite3.Row
    c.executescript(old)
    c.execute("INSERT INTO organizations(name) VALUES ('x')")
    c.executemany("INSERT INTO routine_blocks(org_id,name,start_time,end_time,sort_order) VALUES (1,?,?,?,?)",
                  [("점심·휴식", "12:00", "13:00", 0), ("오후 산책·놀이", "13:00", "16:00", 1), ("하원 준비", "17:00", "20:00", 2)])
    c.commit()
    database.init_db(c); database.init_db(c)
    assert {r["name"]: r["share_prompt"] for r in c.execute("SELECT name, share_prompt FROM routine_blocks")} == {"점심·휴식": 1, "오후 산책·놀이": 0, "하원 준비": 1}

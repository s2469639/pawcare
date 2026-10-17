from datetime import datetime, timedelta

from backend.database import KST, connect
from tests.conftest import ADMIN, MORNING, OTHER_ORG, PARENT_BORI


def today():
    return datetime.now(KST).date()


def view(client, hdr=MORNING):
    return client.get("/api/attendance", headers=hdr).json()


def by_name(v, name):
    return next(d for d in v["dogs"] if d["name"] == name)


def clear_today(client):
    """샘플이 모두 등원한 상태로 시작하므로, 출석 흐름을 보려면 오늘 기록을 비운다."""
    db = connect()
    db.execute("DELETE FROM attendance"); db.commit(); db.close()


def new_dog(client, hdr=MORNING, **kw):
    r = client.post("/api/dogs", json={"name": "쿠폰이", "breed": "푸들", "birth_date": "2022-01-01", "owner_name": "누구", **kw}, headers=hdr)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_seed_all_present_and_weekday_rule(client):
    v = view(client)
    assert v["summary"]["present"] == 5 and all(d["status"] == "present" for d in v["dogs"])
    clear_today(client)
    v = view(client)
    wd = today().weekday()
    expect = "expected" if wd < 5 else None                       # 샘플은 평일(월~금) 이용
    assert all(d["status"] == expect for d in v["dogs"])
    assert by_name(v, "보리")["attend_days"] == [0, 1, 2, 3, 4]


def test_unscheduled_dog_then_manual_add(client):
    clear_today(client)
    did = new_dog(client)                                       # 요일 미설정 → 자동 출석 예정 없음
    d = next(x for x in view(client)["dogs"] if x["id"] == did)
    assert d["status"] is None and d["source"] is None
    added = client.post(f"/api/attendance/{did}/add", headers=MORNING).json()
    assert added["status"] == "expected" and added["source"] == "manual"
    assert client.post(f"/api/attendance/{did}/add", headers=MORNING).json()["status"] == "expected"       # 멱등
    assert client.delete(f"/api/attendance/{did}", headers=MORNING).json()["status"] is None               # 되돌리기


def test_attend_days_set_today_expected(client):
    clear_today(client)
    did = new_dog(client, attend_days=[today().weekday()])
    assert next(x for x in view(client)["dogs"] if x["id"] == did)["source"] == "weekday"
    other = (today().weekday() + 1) % 7
    client.patch(f"/api/dogs/{did}", json={"attend_days": [other]}, headers=MORNING)
    assert next(x for x in view(client)["dogs"] if x["id"] == did)["status"] is None
    client.patch(f"/api/dogs/{did}", json={"attend_days": []}, headers=MORNING)
    assert client.get(f"/api/dogs/{did}", headers=MORNING).json()["attend_days"] == []
    assert client.patch(f"/api/dogs/{did}", json={"attend_days": [7]}, headers=MORNING).status_code == 422
    assert client.post("/api/dogs", json={"name": "x", "breed": "y", "birth_date": "2022-01-01", "owner_name": "z", "attend_days": [-1]}, headers=MORNING).status_code == 422


def test_checkin_checkout_flow(client):
    clear_today(client)
    bori = by_name(view(client), "보리")["id"]
    assert client.post(f"/api/attendance/{bori}/checkout", json={}, headers=MORNING).status_code == 422     # 등원 전 하원 불가
    c = client.post(f"/api/attendance/{bori}/checkin", headers=MORNING).json()
    assert c["status"] == "present" and c["checkin_at"]
    again = client.post(f"/api/attendance/{bori}/checkin", headers=MORNING).json()
    assert again["checkin_at"] == c["checkin_at"]                                                         # 멱등
    o = client.post(f"/api/attendance/{bori}/checkout", json={"pickup_by": " 김서연 ", "note": "물 충분히 마심"}, headers=MORNING).json()
    assert o["checkout_at"] and o["pickup_by"] == "김서연" and o["note"] == "물 충분히 마심"
    assert client.post(f"/api/attendance/{bori}/checkout", json={}, headers=MORNING).status_code == 409
    assert client.post(f"/api/attendance/{bori}/checkout", json={"pickup_by": "가" * 41}, headers=MORNING).status_code == 422
    assert view(client)["summary"]["checked_out"] == 1


def test_absent_rules(client):
    clear_today(client)
    tofu = by_name(view(client), "두부")["id"]
    a = client.post(f"/api/attendance/{tofu}/absent", json={"contacted": True, "note": "병원 방문"}, headers=MORNING).json()
    assert a["status"] == "absent" and a["absent_contacted"] and a["note"] == "병원 방문"
    assert view(client)["summary"]["absent"] == 1
    assert client.post(f"/api/attendance/{tofu}/checkin", headers=MORNING).json()["status"] == "present"     # 결석 처리 후 와도 출석으로 바꿀 수 있다
    assert client.post(f"/api/attendance/{tofu}/absent", json={}, headers=MORNING).status_code == 422       # 출석한 아이는 결석 불가
    assert client.post(f"/api/attendance/{tofu}/absent", json={"note": "가" * 101}, headers=MORNING).status_code == 422


def test_record_auto_checkin_and_routine_targets_present_only(client):
    clear_today(client)
    blocks = client.get("/api/routine", headers=MORNING).json()
    assert blocks["dogs_present"] == 0 and all(b["dogs_total"] == 0 for b in blocks["blocks"])
    first = blocks["blocks"][0]["id"]
    assert client.get(f"/api/routine/{first}", headers=MORNING).json()["dogs"] == []
    bori = by_name(view(client), "보리")["id"]
    r = client.post("/api/records", json={"dog_id": bori, "record_type": "특이사항", "structured_value": "직접 입력", "content": "컨디션 좋음"}, headers=MORNING)
    assert r.status_code == 201
    d = by_name(view(client), "보리")
    assert d["status"] == "present" and d["checkin_at"]                                                     # 기록하면 자동 출석
    assert client.get("/api/routine", headers=MORNING).json()["dogs_present"] == 1
    assert [x["name"] for x in client.get(f"/api/routine/{first}", headers=MORNING).json()["dogs"]] == ["보리"]
    assert client.get("/api/dashboard", headers=MORNING).json()["attending_dogs"] == 1


def test_attendance_access_org_and_discharged(client):
    assert client.get("/api/attendance").status_code == 401
    assert client.get("/api/attendance", headers=PARENT_BORI).status_code == 403
    assert [d["name"] for d in view(client, OTHER_ORG)["dogs"]] == ["구름"]
    bori = by_name(view(client), "보리")["id"]
    assert client.post(f"/api/attendance/{bori}/checkin", headers=OTHER_ORG).status_code == 404            # 다른 유치원 아이
    assert client.post(f"/api/dogs/{bori}/discharge", headers=ADMIN).status_code == 200
    assert client.post(f"/api/attendance/{bori}/checkin", headers=MORNING).status_code == 409               # 퇴원한 아이는 출석 불가
    assert "보리" not in [x["name"] for x in view(client)["dogs"]]
    assert client.get("/api/dashboard", headers=MORNING).json()["attending_dogs"] == 4                      # 출석했어도 퇴원하면 빠진다


def test_hotel_stay_is_scheduled(client):
    clear_today(client)
    cloud = by_name(view(client, OTHER_ORG), "구름")
    assert cloud["status"] == "expected" and cloud["source"] == "stay"                                      # 숙박 기간이면 자동 출석 예정

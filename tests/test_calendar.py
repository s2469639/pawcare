from datetime import datetime, timedelta

from backend.database import KST
from tests.conftest import ADMIN, AFTERNOON, MORNING, OTHER_ORG, PARENT_BORI


def d(n=0):
    return (datetime.now(KST).date() + timedelta(days=n)).isoformat()


def make(client, hdr=None, **kw):
    body = {"title": "테스트 일정", "kind": "event", "start_date": d(1), **kw}
    return client.post("/api/calendar", json=body, headers=hdr or MORNING)


def test_seed_events_present_and_split_by_audience(client):
    month = d(3)[:7]
    staff = client.get(f"/api/calendar?month={month}", headers=MORNING).json()
    assert any(e["title"] == "가을 소풍 산책" for e in staff["events"])
    parent = client.get(f"/api/parent/calendar?month={month}", headers=PARENT_BORI).json()
    assert all("parent_visible" not in e for e in parent["events"])
    assert "내부 시설 점검" not in str(parent)


def test_parent_sees_only_parent_prep_text(client):
    r = make(client, parent_visible=True, prep=[{"audience": "staff", "text": "직원 비밀 준비"}, {"audience": "parent", "text": "간식 지참"}])
    assert r.status_code == 201
    eid = r.json()["id"]
    pr = client.get(f"/api/parent/calendar?month={d(1)[:7]}", headers=PARENT_BORI).json()
    ev = next(e for e in pr["events"] if e["id"] == eid)
    assert ev["prep"] == [{"text": "간식 지참"}]
    assert "직원 비밀 준비" not in str(pr) and "done" not in str(ev)


def test_staff_only_event_hidden_from_parent(client):
    eid = make(client, title="직원 전용", parent_visible=False).json()["id"]
    pr = client.get(f"/api/parent/calendar?month={d(1)[:7]}", headers=PARENT_BORI).json()
    assert eid not in [e["id"] for e in pr["events"]]


def test_validation(client):
    assert make(client, title="  ").status_code == 422
    assert make(client, title="가" * 61).status_code == 422
    assert make(client, start_date="2026-13-40").status_code == 422
    assert make(client, end_date=d(0)).status_code == 422
    assert make(client, start_time="25:00").status_code == 422
    assert make(client, start_time="10:00", end_time="09:00", end_date=d(1)).status_code == 422
    assert make(client, end_time="10:00").status_code == 422
    assert make(client, end_date=d(100)).status_code == 422
    assert make(client, kind="x").status_code == 422
    too_many = [{"audience": "staff", "text": f"t{i}"} for i in range(11)]
    assert make(client, prep=too_many).status_code == 422
    assert make(client, prep=[{"audience": "staff", "text": " "}]).status_code == 422
    assert client.get("/api/calendar?month=2026-1", headers=MORNING).status_code == 422


def test_month_overlap_across_boundary(client):
    eid = make(client, start_date="2031-01-30", end_date="2031-02-02").json()["id"]
    for m in ("2031-01", "2031-02"):
        assert eid in [e["id"] for e in client.get(f"/api/calendar?month={m}", headers=MORNING).json()["events"]]
    for m in ("2030-12", "2031-03"):
        assert eid not in [e["id"] for e in client.get(f"/api/calendar?month={m}", headers=MORNING).json()["events"]]


def test_org_isolation(client):
    eid = make(client).json()["id"]
    assert client.patch(f"/api/calendar/{eid}", json={"title": "x", "kind": "event", "start_date": d(1)}, headers=OTHER_ORG).status_code == 404
    assert client.delete(f"/api/calendar/{eid}", headers=OTHER_ORG).status_code == 404
    other = client.get(f"/api/calendar?month={d(1)[:7]}", headers=OTHER_ORG).json()
    assert other["events"] == []
    evs = client.get(f"/api/calendar?month={d(3)[:7]}", headers=MORNING).json()["events"]
    item = next(e for e in evs if e["title"] == "가을 소풍 산책")["prep"][0]["id"]
    assert client.post(f"/api/calendar/prep/{item}/toggle", headers=OTHER_ORG).status_code == 404


def test_parent_cannot_use_staff_endpoints(client):
    assert client.get("/api/calendar", headers=PARENT_BORI).status_code == 403
    assert client.post("/api/calendar", json={"title": "a", "kind": "event", "start_date": d(1)}, headers=PARENT_BORI).status_code == 403
    assert client.get("/api/parent/calendar", headers=MORNING).status_code == 403
    assert client.get("/api/calendar").status_code == 401


def test_toggle_staff_item_and_block_parent_item(client):
    ev = make(client, parent_visible=True, prep=[{"audience": "staff", "text": "준비"}, {"audience": "parent", "text": "안내"}]).json()
    sid = next(p["id"] for p in ev["prep"] if p["audience"] == "staff")
    pid = next(p["id"] for p in ev["prep"] if p["audience"] == "parent")
    on = client.post(f"/api/calendar/prep/{sid}/toggle", headers=AFTERNOON).json()
    p = next(x for x in on["prep"] if x["id"] == sid)
    assert p["done"] and p["done_by_name"] == "서민재"
    off = client.post(f"/api/calendar/prep/{sid}/toggle", headers=MORNING).json()
    assert not next(x for x in off["prep"] if x["id"] == sid)["done"]
    assert client.post(f"/api/calendar/prep/{pid}/toggle", headers=MORNING).status_code == 422


def test_update_keeps_done_unless_text_changes_and_prep_omitted_keeps_items(client):
    ev = make(client, prep=[{"audience": "staff", "text": "A"}, {"audience": "staff", "text": "B"}]).json()
    a, b = ev["prep"]
    client.post(f"/api/calendar/prep/{a['id']}/toggle", headers=MORNING)
    base = {"title": "수정", "kind": "event", "start_date": d(1)}
    r = client.patch(f"/api/calendar/{ev['id']}", json=base, headers=MORNING).json()      # prep 생략
    assert len(r["prep"]) == 2 and r["title"] == "수정" and next(x for x in r["prep"] if x["id"] == a["id"])["done"]
    r = client.patch(f"/api/calendar/{ev['id']}", json={**base, "prep": [
        {"id": a["id"], "audience": "staff", "text": "A"}, {"id": b["id"], "audience": "staff", "text": "B 변경"}, {"audience": "staff", "text": "C"}]},
        headers=MORNING).json()
    assert [x["text"] for x in r["prep"]] == ["A", "B 변경", "C"] and r["prep"][0]["done"] and not r["prep"][1]["done"]
    r = client.patch(f"/api/calendar/{ev['id']}", json={**base, "prep": []}, headers=MORNING).json()
    assert r["prep"] == []
    bad = client.patch(f"/api/calendar/{ev['id']}", json={**base, "prep": [{"id": 99999, "audience": "staff", "text": "x"}]}, headers=MORNING)
    assert bad.status_code == 422


def test_delete(client):
    eid = make(client, prep=[{"audience": "staff", "text": "A"}]).json()["id"]
    assert client.delete(f"/api/calendar/{eid}", headers=ADMIN).json() == {"ok": True}
    assert client.delete(f"/api/calendar/{eid}", headers=ADMIN).status_code == 404


def test_upcoming_counts_open_staff_prep(client):
    ev = make(client, start_date=d(2), prep=[{"audience": "staff", "text": "A"}, {"audience": "staff", "text": "B"}, {"audience": "parent", "text": "P"}]).json()
    before = client.get("/api/calendar/upcoming?days=7", headers=MORNING).json()
    e = next(x for x in before["events"] if x["id"] == ev["id"])
    assert e["open_prep"] == 2
    client.post(f"/api/calendar/prep/{ev['prep'][0]['id']}/toggle", headers=MORNING)
    after = client.get("/api/calendar/upcoming?days=7", headers=MORNING).json()
    assert next(x for x in after["events"] if x["id"] == ev["id"])["open_prep"] == 1
    assert after["open_prep_total"] == before["open_prep_total"] - 1
    assert client.get("/api/calendar/upcoming?days=0", headers=MORNING).status_code == 422


def test_routine_lists_today_events(client):
    eid = make(client, title="오늘 행사", start_date=d(0), start_time="10:00", end_time="11:00").json()["id"]
    r = client.get("/api/routine", headers=MORNING).json()
    assert eid in [e["id"] for e in r["today_events"]]
    assert all(set(e) == {"id", "title", "kind", "start_time", "end_time"} for e in r["today_events"])


def test_existing_db_without_calendar_gets_seed_once(client):
    from backend.database import connect, init_db
    db = connect()
    db.execute("DROP TABLE calendar_prep_items"); db.execute("DROP TABLE calendar_events"); db.commit()
    init_db(db)
    assert db.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] >= 4
    db.execute("DELETE FROM calendar_prep_items"); db.execute("DELETE FROM calendar_events"); db.commit()
    init_db(db)                                             # 다시 시작해도 직접 지운 일정이 되살아나지 않는다
    assert db.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0] == 0
    db.close()

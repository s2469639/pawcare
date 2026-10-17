from tests.conftest import ADMIN, AFTERNOON, MORNING, PARENT_BORI


def test_notes_are_private_per_staff(client):
    n = client.post("/api/notes", json={"body": "  내일 간식 주문  "}, headers=MORNING)
    assert n.status_code == 201 and n.json()["body"] == "내일 간식 주문"
    nid = n.json()["id"]
    assert [x["id"] for x in client.get("/api/notes", headers=MORNING).json()] == [nid]
    for hdr in (AFTERNOON, ADMIN):                      # 관리자도 남의 메모는 볼 수 없다
        assert client.get("/api/notes", headers=hdr).json() == []
        assert client.patch(f"/api/notes/{nid}", json={"body": "x"}, headers=hdr).status_code == 404
        assert client.delete(f"/api/notes/{nid}", headers=hdr).status_code == 404
    assert client.get("/api/notes", headers=MORNING).json()[0]["body"] == "내일 간식 주문"


def test_notes_access_and_validation(client):
    assert client.get("/api/notes").status_code == 401
    assert client.get("/api/notes", headers=PARENT_BORI).status_code == 403
    assert client.post("/api/notes", json={"body": "x"}, headers=PARENT_BORI).status_code == 403
    assert client.post("/api/notes", json={"body": "   "}, headers=MORNING).status_code == 422
    assert client.post("/api/notes", json={"body": "가" * 1001}, headers=MORNING).status_code == 422


def test_notes_update_delete_and_limit(client):
    nid = client.post("/api/notes", json={"body": "a"}, headers=MORNING).json()["id"]
    assert client.patch(f"/api/notes/{nid}", json={"body": "b"}, headers=MORNING).json()["body"] == "b"
    assert client.delete(f"/api/notes/{nid}", headers=MORNING).json() == {"ok": True}
    assert client.delete(f"/api/notes/{nid}", headers=MORNING).status_code == 404
    for i in range(100):
        assert client.post("/api/notes", json={"body": f"n{i}"}, headers=MORNING).status_code == 201
    assert client.post("/api/notes", json={"body": "넘침"}, headers=MORNING).status_code == 422

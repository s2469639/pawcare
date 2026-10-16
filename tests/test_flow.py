from backend.services import ai_service
from .conftest import ADMIN, AFTERNOON, MORNING, OTHER_ORG

BORI = 1


def new_record(client, content="점심을 평소보다 적게 먹었고 묽은 변을 봤습니다. 오후 담당자는 다음 배변 상태를 확인해 주세요.", **kw):
    body = {"dog_id": BORI, "record_type": "배변", "structured_value": "평소와 다름", "content": content, **kw}
    r = client.post("/api/records", json=body, headers=MORNING)
    assert r.status_code == 201, r.text
    return r.json()


# 테스트 1: 기록 생성
def test_record_create_and_persist(client):
    rec = new_record(client, "테스트 기록")
    recs = client.get(f"/api/dogs/{BORI}/records", headers=MORNING).json()
    assert rec["id"] in [r["id"] for r in recs]
    assert client.get("/api/tasks", headers=MORNING).json()  # 기록 저장만으로 업무가 새로 생기지 않음
    before = len(client.get("/api/tasks", headers=MORNING).json())
    new_record(client, "또 다른 기록")
    assert len(client.get("/api/tasks", headers=MORNING).json()) == before


# 테스트 2: AI 제안 → 무시/승인
def test_ai_suggest_ignore_and_approve(client):
    rec = new_record(client)
    before = len(client.get("/api/tasks", headers=MORNING).json())
    s = client.post("/api/ai/suggest-tasks", json={"record_id": rec["id"]}, headers=MORNING).json()
    assert s["mode"] == "demo" and "AI 아님" in s["mode_label"]
    assert [x["title"] for x in s["suggestions"]] == ["오후 배변 상태 확인"]
    assert s["suggestions"][0]["assignee_id"] == 2
    # 제안만으로는 업무가 생성되지 않는다(= 제안 무시)
    assert len(client.get("/api/tasks", headers=MORNING).json()) == before
    # 승인
    sg = s["suggestions"][0]
    t = client.post("/api/tasks", headers=MORNING, json={
        "dog_id": BORI, "source_record_id": rec["id"], "title": sg["title"], "description": sg["description"],
        "assignee_id": sg["assignee_id"], "ai_suggested": True})
    assert t.status_code == 201
    t = t.json()
    assert t["source_record_id"] == rec["id"] and t["ai_suggested"] is True
    assert t["acknowledgment_status"] == "pending" and t["action_status"] == "todo"
    linked = client.get(f"/api/dogs/{BORI}/records", headers=MORNING).json()
    assert any(x["id"] == rec["id"] and x["tasks"][0]["id"] == t["id"] for x in linked)


# 테스트 3, 4: 확인과 조치는 독립, 완료 시 조치 결과·완료 시각
def test_ack_and_action_are_independent(client):
    t = client.post("/api/tasks", headers=MORNING, json={"dog_id": BORI, "title": "확인", "assignee_id": 2}).json()
    tid = t["id"]
    t = client.post(f"/api/tasks/{tid}/actions", json={"action_type": "acknowledge"}, headers=AFTERNOON).json()
    assert t["acknowledgment_status"] == "acknowledged" and t["action_status"] == "todo"
    assert t["completed_at"] is None
    assert client.post(f"/api/tasks/{tid}/actions", json={"action_type": "acknowledge"}, headers=AFTERNOON).status_code == 409
    t = client.post(f"/api/tasks/{tid}/actions", json={"action_type": "start"}, headers=AFTERNOON).json()
    assert t["action_status"] == "in_progress"
    r = client.post(f"/api/tasks/{tid}/actions", json={"action_type": "complete", "note": "  "}, headers=AFTERNOON)
    assert r.status_code == 422
    assert client.get(f"/api/tasks/{tid}", headers=AFTERNOON).json()["action_status"] == "in_progress"
    t = client.post(f"/api/tasks/{tid}/actions", json={"action_type": "complete", "note": "배변 정상 확인"}, headers=AFTERNOON).json()
    assert t["action_status"] == "completed" and t["completed_at"] and t["completion_note"] == "배변 정상 확인"
    assert [l["action_type"] for l in t["logs"]] == ["created", "acknowledge", "start", "complete"]


def test_complete_without_ack_does_not_acknowledge(client):
    tid = client.post("/api/tasks", headers=MORNING, json={"dog_id": BORI, "title": "x"}).json()["id"]
    t = client.post(f"/api/tasks/{tid}/actions", json={"action_type": "complete", "note": "done"}, headers=MORNING).json()
    assert t["acknowledgment_status"] == "pending" and t["action_status"] == "completed"


def test_reassign_keeps_statuses(client):
    tid = 2  # 확인 완료 + 조치 필요 (샘플)
    before = client.get(f"/api/tasks/{tid}", headers=ADMIN).json()
    t = client.patch(f"/api/tasks/{tid}", json={"assignee_id": 1}, headers=ADMIN).json()
    assert t["assignee_id"] == 1
    assert (t["acknowledgment_status"], t["action_status"]) == (before["acknowledgment_status"], before["action_status"])
    assert t["logs"][-1]["action_type"] == "reassign" and "→" in t["logs"][-1]["note"]
    assert client.patch(f"/api/tasks/{tid}", json={"assignee_id": 4}, headers=ADMIN).status_code == 422  # 타사 직원


# 테스트 5: 데이터 일관성
def test_dashboard_and_dog_consistency(client):
    d0 = client.get("/api/dashboard", headers=AFTERNOON).json()
    assert d0["counts"]["needs_ack"] == 1 and d0["counts"]["mine_pending"] == 1
    client.post("/api/tasks/1/actions", json={"action_type": "acknowledge"}, headers=AFTERNOON)
    d1 = client.get("/api/dashboard", headers=AFTERNOON).json()
    assert d1["counts"]["needs_ack"] == 0 and d1["counts"]["mine_pending"] == 0
    dog_task = [t for t in client.get(f"/api/dogs/{BORI}", headers=AFTERNOON).json()["tasks"] if t["id"] == 1][0]
    dash_task = [t for t in d1["tasks"] if t["id"] == 1][0]
    assert dog_task["acknowledgment_status"] == dash_task["acknowledgment_status"] == "acknowledged"
    assert dog_task["action_status"] == "todo"
    # 목록 정렬: 미확인 → 조치 필요 → 진행 중 → 완료
    ranks = [("pending" if t["acknowledgment_status"] == "pending" and t["action_status"] != "completed" else t["action_status"])
             for t in d0["tasks"]]
    order = {"pending": 0, "todo": 1, "in_progress": 2, "completed": 3}
    assert ranks == sorted(ranks, key=order.get)


def test_filters(client):
    ids = lambda f: {t["id"] for t in client.get(f"/api/tasks?filter={f}", headers=ADMIN).json()}
    assert ids("pending") == {1} and ids("in_progress") == {3} and ids("completed") == {4} and ids("todo") == {1, 2}
    assert len(ids("all")) == 4


# 테스트 6: 오류 처리
def test_validation_and_errors(client):
    r = client.post("/api/records", json={"dog_id": BORI, "record_type": "식사"}, headers=MORNING)
    assert r.status_code == 422
    r = client.post("/api/records", json={"dog_id": BORI, "record_type": "식사", "structured_value": "직접 입력"}, headers=MORNING)
    assert r.status_code == 422
    assert client.post("/api/records", json={"dog_id": BORI, "record_type": "잡담", "content": "x"}, headers=MORNING).status_code == 422
    assert client.post("/api/records", json={"dog_id": 999, "record_type": "식사", "content": "x"}, headers=MORNING).status_code == 404
    assert client.get("/api/dogs/999", headers=MORNING).status_code == 404
    assert client.get("/api/tasks/999", headers=MORNING).status_code == 404
    assert client.post("/api/tasks", json={"dog_id": BORI, "title": "  "}, headers=MORNING).status_code == 422
    assert client.get("/api/dogs").status_code == 401
    assert client.get("/api/dogs", headers={"X-Staff-Id": "999"}).status_code == 401
    assert client.post("/api/tasks", json={"dog_id": BORI, "title": "t", "source_record_id": 3}, headers=MORNING).status_code == 422  # 다른 반려견 기록


# 회사(유치원) 단위 격리
def test_org_isolation(client):
    assert client.get(f"/api/dogs/{BORI}", headers=OTHER_ORG).status_code == 404
    assert {d["name"] for d in client.get("/api/dogs", headers=OTHER_ORG).json()} == {"구름"}
    assert client.get("/api/tasks/1", headers=OTHER_ORG).status_code == 404
    assert all(t["dog_name"] == "구름" for t in client.get("/api/tasks", headers=OTHER_ORG).json())
    assert client.post("/api/tasks/1/actions", json={"action_type": "acknowledge"}, headers=OTHER_ORG).status_code == 404
    assert client.post("/api/ai/suggest-tasks", json={"record_id": 1}, headers=OTHER_ORG).status_code == 404


def test_dog_search_and_filter(client):
    assert [d["name"] for d in client.get("/api/dogs?q=보", headers=MORNING).json()] == ["보리"]
    assert [d["name"] for d in client.get("/api/dogs?status=needs_check", headers=MORNING).json()] == ["보리"]
    assert client.get("/api/dogs?status=bogus", headers=MORNING).status_code == 422


# 보호자 공개 범위
def test_parent_preview_only_approved(client):
    rid = new_record(client, "내부 메모: 직원끼리만 공유")["id"]
    p = client.get("/api/parent/dogs/1/preview").json()
    assert p["records"] == []
    assert client.patch(f"/api/records/{rid}/parent-approval", json={"action": "approve"}, headers=MORNING).status_code == 422
    client.patch(f"/api/records/{rid}/parent-approval", json={"action": "approve", "parent_text": "오늘도 잘 지냈어요."}, headers=MORNING)
    p = client.get("/api/parent/dogs/1/preview").json()
    assert [r["parent_text"] for r in p["records"]] == ["오늘도 잘 지냈어요."]
    assert "내부 메모" not in str(p) and "tasks" not in p
    client.patch(f"/api/records/{rid}/parent-approval", json={"action": "revoke"}, headers=MORNING)
    assert client.get("/api/parent/dogs/1/preview").json()["records"] == []


def test_ai_does_not_invent_or_diagnose(client):
    # 정보 부족 / 이상 없음 → 제안 없음
    rec = new_record(client, "잘 지냈습니다.", record_type="기타", structured_value=None)
    s = client.post("/api/ai/suggest-tasks", json={"record_id": rec["id"]}, headers=MORNING).json()
    assert s["suggestions"] == [] and s["notice"]
    # 모델 출력 검증: 원문에 없는 근거 / 진단·투약 표현은 폐기
    record = {"record_type": "배변", "structured_value": None, "content": "묽은 변이 관찰되었습니다."}
    staff = [{"id": 2, "role": "오후 담당자", "name": "x"}]
    out = ai_service.sanitize_model_output({"suggestions": [
        {"title": "장염 의심 확인", "description": "진단 필요", "evidence": ["묽은 변이 관찰되었습니다."]},
        {"title": "배변 확인", "description": "관찰 후 기록", "evidence": ["구토를 했습니다."]},
        {"title": "배변 확인", "description": "관찰 후 기록", "assignee_role": "오후 담당자", "evidence": ["묽은 변이 관찰되었습니다."]},
    ], "facts": ["묽은 변이 관찰되었습니다.", "열이 있었습니다."]}, record, staff)
    assert len(out["suggestions"]) == 1 and out["suggestions"][0]["assignee_id"] == 2
    assert out["facts"] == ["묽은 변이 관찰되었습니다."]


def test_gemini_failure_falls_back_to_demo(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "bad")
    monkeypatch.setenv("GEMINI_MODEL", "m")
    monkeypatch.setattr(ai_service, "_gemini", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    s = client.post("/api/ai/suggest-tasks", json={"record_id": 2}, headers=MORNING).json()
    assert s["mode"] == "demo" and "대체" in s["fallback_note"]


def test_reset(client):
    client.post("/api/tasks", headers=MORNING, json={"dog_id": BORI, "title": "임시"})
    assert client.post("/api/demo/reset").status_code == 200
    assert len(client.get("/api/tasks", headers=ADMIN).json()) == 4

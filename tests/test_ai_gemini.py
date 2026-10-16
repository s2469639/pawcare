"""Gemini 연동: 실패 원인 안내, 모델 이름 정리, JSON 모드 재시도, 응답 해석, 근거 검증. (실제 호출 없이 응답을 흉내 낸다)"""
import json

import httpx
import pytest

from backend.services import ai_service
from .conftest import MORNING, PARENT_BORI

KEY = "AIzaSy-SECRET-TEST-KEY-0123456789"
GOOD = {"summary": "묽은 변이 관찰됨", "facts": ["묽은 변이 관찰되었습니다"],
        "suggestions": [{"title": "오후 배변 상태 확인", "description": "다음 배변 상태를 관찰하고 기록합니다.",
                         "assignee_role": "오후 담당자", "evidence": ["오후 담당자는 다음 배변 상태를 확인해 주세요"]}], "notice": None}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def ok(payload, fenced=False, extra_parts=()):
    text = json.dumps(payload, ensure_ascii=False)
    return Resp(200, {"candidates": [{"content": {"parts": [*extra_parts, {"text": f"```json\n{text}\n```" if fenced else text}]}}]})


def err(status, message):
    return Resp(status, {"error": {"code": status, "message": message}})


@pytest.fixture()
def gem(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    calls = []

    def install(*responses):
        queue = list(responses)

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append({"url": url, "json": json, "headers": headers})
            r = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(ai_service.httpx, "post", fake_post)
        return calls
    return install


def suggest(client, record=2):
    return client.post("/api/ai/suggest-tasks", json={"record_id": record}, headers=MORNING).json()


def test_success_handles_code_fence_thought_parts_and_loose_evidence(client, gem):
    calls = gem(ok(GOOD, fenced=True, extra_parts=[{"text": "(생각 요약)", "thought": True}]))      # 코드블록 + 생각 파트 + 마침표 없는 근거
    r = suggest(client)
    assert r["mode"] == "gemini" and "gemini-test" in r["mode_label"] and "fallback_note" not in r
    assert [s["title"] for s in r["suggestions"]] == ["오후 배변 상태 확인"] and r["suggestions"][0]["assignee_id"] == 2
    assert calls[0]["headers"]["x-goog-api-key"] == KEY and calls[0]["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert KEY not in json.dumps(r)                                                         # 키는 응답에 나오지 않는다


def test_model_name_from_ai_studio_list_is_normalized(client, gem, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", " models/gemini-test ")
    calls = gem(ok(GOOD))
    assert suggest(client)["mode"] == "gemini"
    assert calls[0]["url"].endswith("/v1beta/models/gemini-test:generateContent")           # models/models/… 가 되지 않음


def test_retries_without_json_mode_when_model_rejects_it(client, gem):
    calls = gem(err(400, "JSON mode is not enabled for models/gemma-x"), ok(GOOD, fenced=True))
    r = suggest(client)
    assert r["mode"] == "gemini" and len(calls) == 2
    assert "responseMimeType" in calls[0]["json"]["generationConfig"] and "responseMimeType" not in calls[1]["json"]["generationConfig"]


@pytest.mark.parametrize("response, expect", [
    (err(400, "API key not valid. Please pass a valid API key."), "API 키가 올바르지 않습니다"),
    (err(403, "Permission denied"), "키가 거부되었습니다"),
    (err(404, "models/gemini-test is not found"), "gemini-test"),
    (err(429, "Resource has been exhausted (e.g. check quota)."), "사용량 한도"),
    (err(503, "The model is overloaded."), "일시적으로"),
    (err(400, "User location is not supported for the API use."), "지역"),
    (Resp(200, {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}), "SAFETY"),
    (Resp(200, {"candidates": [{"content": {"parts": [{"text": "   "}]}, "finishReason": "MAX_TOKENS"}]}), "MAX_TOKENS"),
    (Resp(200, {"candidates": [{"content": {"parts": [{"text": "죄송하지만 JSON이 아닙니다"}]}}]}), "해석하지 못했습니다"),
    (httpx.ReadTimeout("slow"), "시간이 초과"),
    (httpx.ConnectError("down"), "연결하지 못했습니다"),
])
def test_failures_explain_the_cause_and_fall_back_to_demo(client, gem, response, expect):
    gem(response)
    r = suggest(client)
    assert r["mode"] == "demo" and "데모 분석" in r["mode_label"]
    assert "원인" in r["fallback_note"] and expect in r["fallback_note"], r["fallback_note"]
    assert [s["title"] for s in r["suggestions"]] == ["오후 배변 상태 확인"]               # 흐름은 막히지 않고 규칙 기반 제안이 나온다
    assert KEY not in json.dumps(r)


def test_all_suggestions_rejected_falls_back_instead_of_showing_nothing(client, gem):
    bad = dict(GOOD, suggestions=[{"title": "장염 의심 확인", "description": "진단 필요", "assignee_role": None, "evidence": ["기록에 없는 문장입니다"]}])
    gem(ok(bad))
    r = suggest(client)
    assert r["mode"] == "demo" and "근거" in r["fallback_note"]
    assert [s["title"] for s in r["suggestions"]] == ["오후 배변 상태 확인"]


def test_model_that_finds_nothing_is_not_treated_as_failure(client, gem):
    gem(ok({"summary": "", "facts": [], "suggestions": [], "notice": "후속 확인이 필요한 사항이 없습니다."}))
    r = suggest(client)
    assert r["mode"] == "gemini" and r["suggestions"] == [] and r["notice"] == "후속 확인이 필요한 사항이 없습니다."


def test_missing_model_is_explained(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY); monkeypatch.setenv("GEMINI_MODEL", "")
    r = suggest(client)
    assert r["mode"] == "demo" and "GEMINI_MODEL" in r["fallback_note"] and "list_models" in r["fallback_note"]


def test_failure_is_logged_without_the_key(client, gem, caplog):
    gem(err(429, f"quota exceeded for key {KEY[:8]}"))
    with caplog.at_level("WARNING"):
        suggest(client)
    assert "Gemini 호출 실패" in caplog.text and KEY not in caplog.text


# ---------------- 연결 테스트 API ----------------
def test_connection_test_endpoint(client, gem, monkeypatch):
    assert client.post("/api/ai/test").status_code == 401
    assert client.post("/api/ai/test", headers=PARENT_BORI).status_code == 403
    monkeypatch.delenv("GEMINI_API_KEY"); 
    r = client.post("/api/ai/test", headers=MORNING).json()
    assert r["ok"] is False and r["key_set"] is False and "GEMINI_API_KEY" in r["message"]
    monkeypatch.setenv("GEMINI_API_KEY", KEY); monkeypatch.setenv("GEMINI_MODEL", "")
    r = client.post("/api/ai/test", headers=MORNING).json()
    assert r["ok"] is False and r["key_set"] and not r["model_set"] and "GEMINI_MODEL" in r["message"]
    monkeypatch.setenv("GEMINI_MODEL", "models/gemini-test")
    gem(ok(GOOD))
    r = client.post("/api/ai/test", headers=MORNING).json()
    assert r["ok"] is True and r["model"] == "gemini-test" and "정상" in r["message"] and KEY not in json.dumps(r)
    gem(err(429, "quota"))
    r = client.post("/api/ai/test", headers=MORNING).json()
    assert r["ok"] is False and "한도" in r["message"]


# ---------------- 모델 자동 탐색 (목록에는 있어도 호출은 404인 경우) ----------------
@pytest.fixture(autouse=True)
def _reset_auto_cache():
    ai_service._auto_cache.update(model=None, at=0.0)
    yield
    ai_service._auto_cache.update(model=None, at=0.0)


LISTED = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash-preview",
          "gemini-3.5-flash-image", "gemma-3-27b-it", "gemini-embedding-001"]


@pytest.fixture()
def google(monkeypatch):
    """models: 모델 이름 → 'ok' 또는 HTTP 상태 코드. 목록(GET)에는 항상 LISTED 전체가 나온다."""
    state = {"models": {}, "posts": [], "gets": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        state["gets"] += 1
        items = [{"name": f"models/{n}", "supportedGenerationMethods": ["embedContent"] if "embedding" in n else ["generateContent"]} for n in LISTED]
        return Resp(200, {"models": items})

    def fake_post(url, headers=None, json=None, timeout=None):
        model = url.split("/models/")[1].split(":")[0]
        state["posts"].append(model)
        v = state["models"].get(model, 404)
        return ok(GOOD) if v == "ok" else err(v, f"models/{model} is not found" if v == 404 else "quota")
    monkeypatch.setattr(ai_service.httpx, "get", fake_get)
    monkeypatch.setattr(ai_service.httpx, "post", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    return state


def test_find_working_models_skips_dead_models_even_if_listed(google):
    google["models"].update({"gemini-3.5-flash": "ok", "gemini-3.1-flash-lite": 429, "gemini-2.5-pro": "ok"})     # 2.5-flash는 목록에 있지만 404
    r = ai_service.find_working_models(KEY)
    assert r["working"] == ["gemini-3.5-flash", "gemini-2.5-pro"]
    tried = {t["model"]: t for t in r["tried"]}
    assert tried["gemini-2.5-flash"]["result"] == "404" and "사용 불가" in tried["gemini-2.5-flash"]["note"]
    assert tried["gemini-3.1-flash-lite"]["result"] == "429" and "한도" in tried["gemini-3.1-flash-lite"]["note"]
    assert not any(x in " ".join(google["posts"]) for x in ("image", "gemma", "embedding"))                      # 이미지·임베딩·gemma는 후보에서 제외
    assert r["listed"] == 5
    assert google["posts"].index("gemini-3.6-flash-preview") > google["posts"].index("gemini-2.5-pro")          # 미리보기 버전은 정식 버전 뒤


def test_find_stops_when_enough_found(google):
    google["models"].update({"gemini-3.5-flash": "ok", "gemini-3.1-flash-lite": "ok", "gemini-2.5-flash": "ok", "gemini-2.5-pro": "ok"})
    assert ai_service.find_working_models(KEY, want=2)["working"] == ["gemini-3.5-flash", "gemini-3.1-flash-lite"]
    assert len(google["posts"]) == 2


def test_auto_model_picks_a_working_model_and_caches_it(client, google, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "auto")
    google["models"].update({"gemini-3.5-flash": "ok"})
    r = suggest(client)
    assert r["mode"] == "gemini" and "gemini-3.5-flash" in r["mode_label"] and "fallback_note" not in r
    gets = google["gets"]
    r2 = suggest(client)                                                                        # 두 번째는 기억한 모델을 바로 사용(목록 재조회 없음)
    assert r2["mode"] == "gemini" and google["gets"] == gets


def test_auto_model_rediscovers_when_cached_model_is_retired(client, google, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "auto")
    google["models"].update({"gemini-3.5-flash": "ok", "gemini-2.5-pro": "ok"})
    assert "gemini-3.5-flash" in suggest(client)["mode_label"]
    google["models"]["gemini-3.5-flash"] = 404                                                  # 그새 종료됨
    r = suggest(client)
    assert r["mode"] == "gemini" and "gemini-2.5-pro" in r["mode_label"]


def test_auto_model_with_nothing_working_explains(client, google, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "auto")
    r = suggest(client)                                                                         # 모든 모델이 404
    assert r["mode"] == "demo" and "사용할 수 있는 Gemini 모델을 찾지 못했습니다" in r["fallback_note"] and "사용 불가" in r["fallback_note"]


def test_404_for_a_fixed_model_points_to_find_and_auto(client, google, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")                                        # 이름은 맞지만 종료됨
    note = suggest(client)["fallback_note"]
    assert "gemini-2.5-flash" in note and "--find" in note and "GEMINI_MODEL=auto" in note and "종료" in note


def test_find_models_endpoint(client, google, monkeypatch):
    assert client.post("/api/ai/find-models").status_code == 401
    assert client.post("/api/ai/find-models", headers=PARENT_BORI).status_code == 403
    google["models"].update({"gemini-3.5-flash": "ok"})
    r = client.post("/api/ai/find-models", headers=MORNING).json()
    assert r["ok"] and r["working"] == ["gemini-3.5-flash"] and KEY not in json.dumps(r)
    monkeypatch.delenv("GEMINI_API_KEY")
    r = client.post("/api/ai/find-models", headers=MORNING).json()
    assert r["ok"] is False and "GEMINI_API_KEY" in r["message"]


def test_connection_test_shows_resolved_model_for_auto(client, google, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "auto")
    google["models"].update({"gemini-3.5-flash": "ok"})
    r = client.post("/api/ai/test", headers=MORNING).json()
    assert r["ok"] and r["model"] == "gemini-3.5-flash" and "gemini-3.5-flash" in r["message"]


def test_assignee_is_only_set_when_the_record_mentions_it(client, gem):
    """모델이 담당자를 정해 와도, 기록 원문에 그 역할이 언급되지 않았으면 지정하지 않는다(기록 #1에는 담당자 언급이 없음)."""
    pick = dict(GOOD, suggestions=[{"title": "식사량 추가 관찰", "description": "다음 식사 시 섭취량을 관찰하고 기록한다.",
                                    "assignee_role": "오후 담당자", "evidence": ["점심을 평소보다 적게 먹었습니다."]}])
    gem(ok(pick))
    r = suggest(client, record=1)
    assert r["mode"] == "gemini" and [s["title"] for s in r["suggestions"]] == ["식사량 추가 관찰"]
    assert r["suggestions"][0]["assignee_id"] is None and "담당자 정보가 없어" in r["suggestions"][0]["assignee_note"]
    gem(ok(GOOD))                                                                           # 기록 #2는 '오후 담당자는 …'라고 적혀 있으므로 지정된다
    assert suggest(client, record=2)["suggestions"][0]["assignee_id"] == 2


def test_role_in_source_rules():
    f = ai_service._role_in_source
    assert f("오후 담당자", "오후 담당자는 확인해 주세요") and f("오전 담당자", "오전 담당 선생님께 전달") and f("관리자", "관리자에게 보고")
    assert not f("오후 담당자", "오후 활동량이 적었습니다")        # 시간대 표현일 뿐 담당자를 가리키지 않음
    assert not f("오후 담당자", "점심을 적게 먹었습니다") and not f(None, "오후 담당자") and not f("오전 담당자", "오후 담당자는")

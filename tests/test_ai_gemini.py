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

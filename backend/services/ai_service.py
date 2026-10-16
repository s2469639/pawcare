"""기록 기반 후속 업무 제안.

- 기본: 규칙 기반 '데모 분석'(실제 AI 아님).
- GEMINI_API_KEY + GEMINI_MODEL 이 서버 환경변수에 있으면 Gemini 호출.
- 어떤 경우에도 제안은 DB에 저장하지 않는다. 직원이 승인(업무로 등록)해야 업무가 된다.
- 근거 문장은 반드시 원본 기록에 실제로 있는 문장만 허용한다(없는 사실 생성 방지).
"""
import json
import logging
import os
import re
from typing import Optional

import httpx

FORBIDDEN = re.compile(r"진단|질환|질병|감염|처방|투약|투여|\bmg\b|약을|병원에 가|수의사 처방")

DOMAINS = {
    "stool": {"base": "배변 상태", "desc": "다음 배변 상태를 관찰하고 결과를 기록합니다.",
              "kw": r"배변|변이|묽|설사|대변|소변", "abn": r"묽|설사|평소와 다름|이상|다르"},
    "meal": {"base": "식사량", "desc": "다음 식사 때 식사량을 확인하고 결과를 기록합니다.",
             "kw": r"식사|먹|사료|급여|식욕|남겼", "abn": r"적게|안 먹|먹지 않|식욕|남겼|급여 방식|참고사항"},
    "activity": {"base": "활동 상태", "desc": "활동 상태를 관찰하고 결과를 기록합니다.",
                 "kw": r"활동|산책|놀이|기운|무기력", "abn": r"활동량이 적|활동.{0,4}(적|줄)|무기력|기운이 없|관찰"},
    "behavior": {"base": "행동 상태", "desc": "행동 상태를 관찰하고 결과를 기록합니다.",
                 "kw": r"행동|짖|공격|불안|떨|숨", "abn": r"짖|공격|불안|떨|숨"},
    "vomit": {"base": "구토 이후 상태", "desc": "이후 식사와 배변 상태를 관찰하고 결과를 기록합니다.",
              "kw": r"구토|토했|토함", "abn": r"구토|토했|토함"},
}
REQUEST_RE = re.compile(r"확인해\s*(주|줘|달)|관찰(이)?\s*(필요|해)|지켜봐|살펴봐|체크|확인이\s*필요|확인할\s*필요")
TYPE_TO_DOMAIN = {"배변": "stool", "식사": "meal", "활동": "activity", "행동": "behavior"}
POSITIVE = re.compile(r"^(잘 먹음|정상|활발함|평소와 비슷함)$")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+", text) if s.strip()]


def _assignee_from(text: str, staff: list[dict]) -> Optional[dict]:
    for key in ("오후", "오전", "관리자"):
        if key in text:
            for s in staff:
                if key in s["role"]:
                    return s
    return None


def demo_analyze(record: dict, staff: list[dict]) -> dict:
    sv = (record.get("structured_value") or "").strip()
    content = record["content"]
    sents = _sentences(content)
    notice = None
    suggestions: list[dict] = []

    explicit: dict[str, tuple[str, bool]] = {}   # domain -> (근거문장, 오후여부)
    abnormal: dict[str, str] = {}
    for s in sents:
        is_req = bool(REQUEST_RE.search(s))
        for key, d in DOMAINS.items():
            if re.search(d["kw"], s):
                if is_req:
                    explicit.setdefault(key, (s, "오후" in s))
                if re.search(d["abn"], s):
                    abnormal.setdefault(key, s)
        if is_req and not any(re.search(d["kw"], s) for d in DOMAINS.values()):
            dk = TYPE_TO_DOMAIN.get(record["record_type"])
            if dk:
                explicit.setdefault(dk, (s, "오후" in s))
    # 구조화 값이 이상 신호인 경우 (선택값 그대로만 사용)
    dk = TYPE_TO_DOMAIN.get(record["record_type"])
    if dk and sv and not POSITIVE.match(sv) and sv != "직접 입력" and sv in (
            "평소보다 적게 먹음", "먹지 않음", "평소와 다름", "관찰 필요", "활동량이 적음"):
        abnormal.setdefault(dk, f"{record['record_type']}: {sv}")

    chosen = explicit if explicit else dict(list(abnormal.items())[:2])
    for key, val in chosen.items():
        d = DOMAINS[key]
        sent, pm = val if isinstance(val, tuple) else (val, "오후" in val)
        asg = _assignee_from(sent, staff) or _assignee_from(content, staff)
        title = f"{'오후 ' if pm else ''}{d['base']} 확인"
        suggestions.append({
            "title": title, "description": d["desc"], "needs_check": True,
            "assignee_id": asg["id"] if asg else None,
            "assignee_note": None if asg else "기록에 담당자 정보가 없어 지정이 필요합니다.",
            "priority": "high" if len(abnormal) >= 2 else "normal",
            "evidence": [sent],
        })

    facts = list(dict.fromkeys([sv_text for sv_text in ([f"{record['record_type']}: {sv}"] if sv and sv != "직접 입력" else [])] + sents))
    summary = " ".join(sents)[:200] if sents else sv
    if not suggestions:
        if len(content) < 6 and (not sv or sv == "직접 입력"):
            notice = "기록 내용이 부족해 후속 업무를 제안하지 않았습니다. 확인이 필요하면 내용을 보완하거나 직접 업무를 등록해 주세요."
        else:
            notice = "기록에서 후속 확인이 필요한 사항이 확인되지 않아 제안하지 않았습니다. 필요하면 직접 업무를 등록할 수 있습니다."
    return {"summary": summary, "facts": facts, "suggestions": suggestions, "notice": notice}


# ---------------- Gemini ----------------
PROMPT = """너는 반려견 유치원 직원의 돌봄 기록을 읽고 후속 확인 업무를 '제안'하는 보조 도구다.
규칙:
- 기록에 있는 사실만 사용한다. 기록에 없는 증상·사실을 추가하지 않는다.
- 질병을 진단하거나 원인을 추정하지 않는다. 약물, 투여량, 투여 시각을 정하지 않는다.
- 이미 수행된 것처럼 쓰지 않는다. 업무는 '관찰하고 기록한다' 수준의 확인 행동만 제안한다.
- 정보가 부족하면 suggestions를 빈 배열로 두고 notice에 이유를 쓴다.
- evidence에는 기록 원문에 실제로 있는 문장을 그대로(수정 없이) 넣는다.
- assignee_role은 기록에 근거가 있을 때만 [{roles}] 중 하나, 아니면 null.
JSON만 출력: {{"summary":str,"facts":[str],"suggestions":[{{"title":str,"description":str,"assignee_role":str|null,"evidence":[str]}}],"notice":str|null}}

반려견: {dog}
기록 유형: {rtype}
선택 값: {sv}
기록 내용: {content}"""


class AIError(Exception):
    """Gemini 호출 실패. user_message는 화면에 보여줄 원인(키 값은 절대 포함하지 않는다), detail은 서버 로그용."""

    def __init__(self, user_message: str, detail: str = "", status: int = 0):
        super().__init__(user_message)
        self.user_message, self.detail, self.status = user_message, detail, status


def _clean_model(model: str) -> str:
    """AI Studio 목록의 'models/gemini-…' 형태로 넣어도 동작하도록 접두어를 떼고 공백을 정리한다."""
    return model.strip().removeprefix("models/").strip("/ ")


def _error_message(status: int, body, model: str) -> tuple[str, str]:
    msg = ""
    try:
        msg = str((body or {}).get("error", {}).get("message", ""))
    except AttributeError:
        pass
    low = msg.lower()
    if status == 400 and ("api key" in low or "api_key" in low):
        return "API 키가 올바르지 않습니다. 키를 다시 복사해 .env의 GEMINI_API_KEY에 넣어 주세요(따옴표·공백 없이).", msg
    if "location" in low and "not supported" in low:
        return "이 지역에서는 Gemini API를 사용할 수 없다는 응답입니다.", msg
    if status in (401, 403):
        return "키가 거부되었습니다(권한 없음·사용 제한). Google AI Studio에서 키의 상태와 제한 설정을 확인해 주세요.", msg
    if status == 404:
        return f"모델 '{model}'을(를) 찾을 수 없습니다. `python -m backend.list_models`로 내 키로 쓸 수 있는 이름을 확인해 .env의 GEMINI_MODEL에 넣어 주세요.", msg
    if status == 429:
        return "무료 사용량 한도(분당·일일)를 넘었습니다. 잠시 뒤 다시 시도하거나 다른 모델로 바꿔 보세요.", msg
    if status >= 500:
        return "Google 서버가 일시적으로 응답하지 못했습니다. 잠시 뒤 다시 시도해 주세요.", msg
    return f"요청이 거부되었습니다 (HTTP {status}). {msg[:120]}".strip(), msg


def _post(model: str, key: str, prompt: str, json_mode: bool) -> dict:
    cfg = {"temperature": 0.2}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    try:
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                       json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}, timeout=30)
    except httpx.TimeoutException as e:
        raise AIError("응답 시간이 초과되었습니다(30초). 잠시 뒤 다시 시도해 주세요.", type(e).__name__) from e
    except httpx.HTTPError as e:
        raise AIError("Google에 연결하지 못했습니다. 인터넷 연결이나 방화벽을 확인해 주세요.", type(e).__name__) from e
    try:
        body = r.json()
    except ValueError:
        body = None
    if r.status_code != 200:
        user, detail = _error_message(r.status_code, body, model)
        raise AIError(user, detail, r.status_code)
    return body or {}


def _extract_json(text: str) -> dict:
    """모델이 ```json 코드블록이나 설명 문장으로 감싸 보내도 JSON 본문만 꺼낸다."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        raise AIError("AI 응답을 해석하지 못했습니다(JSON 형식이 아님).", t[:80])
    try:
        data = json.loads(t[i:j + 1])
    except ValueError as e:
        raise AIError("AI 응답을 해석하지 못했습니다(JSON 형식 오류).", t[:80]) from e
    if not isinstance(data, dict):
        raise AIError("AI 응답을 해석하지 못했습니다(예상한 형식이 아님).", "")
    return data


def _gemini(record: dict, dog: dict, staff: list[dict], key: str, model: str) -> dict:
    model = _clean_model(model)
    prompt = PROMPT.format(roles=", ".join(s["role"] for s in staff), dog=dog["name"],
                           rtype=record["record_type"], sv=record.get("structured_value") or "-",
                           content=record["content"])
    try:
        body = _post(model, key, prompt, json_mode=True)
    except AIError as e:
        # 일부 모델은 JSON 모드를 지원하지 않는다 → 같은 요청을 일반 모드로 한 번 더 시도(응답은 직접 JSON으로 해석)
        if e.status == 400 and ("json mode" in e.detail.lower() or "mime" in e.detail.lower()):
            body = _post(model, key, prompt, json_mode=False)
        else:
            raise
    cands = body.get("candidates") or []
    if not cands:
        reason = (body.get("promptFeedback") or {}).get("blockReason")
        raise AIError(f"AI가 응답하지 않았습니다{f' (차단 사유: {reason})' if reason else ''}. 요청이 안전 필터에 막혔을 수 있습니다.", str(body)[:120])
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise AIError(f"AI가 빈 응답을 보냈습니다 (종료 사유: {cands[0].get('finishReason', '알 수 없음')}).", "")
    return sanitize_model_output(_extract_json(text), record, staff)


def _norm(s: str) -> str:
    """근거 문장 비교용: 공백·따옴표·문장부호 차이는 무시한다(내용이 원문에 있는지만 본다)."""
    return re.sub(r"[\s\"'“”‘’.,!?…·~\-]+", "", s)


def sanitize_model_output(data: dict, record: dict, staff: list[dict]) -> dict:
    """모델 출력 검증: 원문에 없는 근거·금지 표현이 있으면 해당 제안을 버린다. 버린 개수는 rejected로 알려준다."""
    source = (record.get("structured_value") or "") + "\n" + record["content"]
    src_norm = _norm(source)
    in_source = lambda e: isinstance(e, str) and bool(_norm(e)) and _norm(e) in src_norm
    by_role = {s["role"]: s for s in staff}
    out, rejected = [], 0
    for s in (data.get("suggestions") or [])[:3]:
        title, desc = str(s.get("title", "")).strip()[:80], str(s.get("description", "")).strip()[:500]
        ev = [e.strip() for e in (s.get("evidence") or []) if in_source(e)]
        if not title or not ev or FORBIDDEN.search(title + desc):
            rejected += 1
            continue
        asg = by_role.get(s.get("assignee_role"))
        out.append({"title": title, "description": desc, "needs_check": True,
                    "assignee_id": asg["id"] if asg else None,
                    "assignee_note": None if asg else "기록에 담당자 정보가 없어 지정이 필요합니다.",
                    "priority": "normal", "evidence": ev})
    facts = [f.strip() for f in (data.get("facts") or []) if in_source(f)]
    summary = str(data.get("summary", ""))[:300]
    if FORBIDDEN.search(summary):
        summary = ""
    notice = data.get("notice") if isinstance(data.get("notice"), str) else None
    if not out and not notice:
        notice = "기록에서 후속 확인이 필요한 사항이 확인되지 않았습니다."
    return {"summary": summary, "facts": facts, "suggestions": out, "notice": notice, "rejected": rejected}


_log = logging.getLogger("uvicorn.error")


def suggest(record: dict, dog: dict, staff: list[dict]) -> dict:
    key, model = os.environ.get("GEMINI_API_KEY", "").strip(), os.environ.get("GEMINI_MODEL", "").strip()
    fallback_note = None
    if key and model:
        try:
            res = _gemini(record, dog, staff, key, model)
            rejected = res.pop("rejected", 0)
            if res["suggestions"] or not rejected:
                res["mode"], res["mode_label"] = "gemini", f"Gemini 분석 ({_clean_model(model)})"
                return res
            # AI가 제안은 했지만 모두 검증(원문 근거·금지 표현)을 통과하지 못했다 → 안전한 규칙 기반 분석으로 대체
            fallback_note = "AI 제안이 원본 기록의 근거와 맞지 않아(또는 금지 표현 포함) 사용하지 않고 데모 분석(규칙 기반)으로 대체했습니다."
            _log.warning("Gemini 제안 %d건이 검증을 통과하지 못했습니다.", rejected)
        except AIError as e:
            fallback_note = f"AI 호출에 실패해 데모 분석(규칙 기반)으로 대체했습니다. 원인: {e.user_message}"
            _log.warning("Gemini 호출 실패: %s | %s", e.user_message, e.detail)
        except Exception as e:    # 예상 밖 오류도 사용자 흐름을 막지 않는다. 서버 로그에 남긴다(키는 포함되지 않음).
            fallback_note = "AI 호출 중 예기치 못한 오류가 나서 데모 분석(규칙 기반)으로 대체했습니다. 서버 터미널의 로그를 확인해 주세요."
            _log.warning("Gemini 처리 중 예외: %s: %s", type(e).__name__, str(e)[:120])
    elif key and not model:
        fallback_note = "GEMINI_MODEL이 설정되지 않아 데모 분석(규칙 기반)을 사용했습니다. `python -m backend.list_models`로 모델 이름을 확인해 .env에 넣어 주세요."
    res = demo_analyze(record, staff)
    res["mode"], res["mode_label"] = "demo", "데모 분석 (규칙 기반 · 실제 AI 아님)"
    if fallback_note:
        res["fallback_note"] = fallback_note
    return res


def check_connection() -> dict:
    """설정과 실제 연결 상태를 점검한다(작은 예시 기록으로 1회 호출 → 무료 한도를 아주 조금 사용)."""
    key, model = os.environ.get("GEMINI_API_KEY", "").strip(), os.environ.get("GEMINI_MODEL", "").strip()
    out = {"key_set": bool(key), "model_set": bool(model), "model": _clean_model(model) if model else "", "ok": False, "message": ""}
    if not key:
        out["message"] = "GEMINI_API_KEY가 설정되지 않았습니다. 프로젝트 맨 위 폴더의 .env에 키를 넣고 서버를 껐다 켜 주세요. (데모 분석으로 동작 중)"
        return out
    if not model:
        out["message"] = "GEMINI_MODEL이 비어 있습니다. `python -m backend.list_models`로 이름을 확인해 .env에 넣어 주세요."
        return out
    sample = {"record_type": "배변", "structured_value": "평소와 다름", "content": "묽은 변이 관찰되었습니다. 오후 담당자는 다음 배변 상태를 확인해 주세요."}
    try:
        res = _gemini(sample, {"name": "연결 테스트"}, [{"id": 0, "name": "-", "role": "오후 담당자"}], key, model)
        n = len(res["suggestions"])
        out.update(ok=True, message=f"Gemini가 정상 응답했습니다. (예시 기록에서 제안 {n}건{'' if n else ', 검증을 통과한 제안은 없음'})")
    except AIError as e:
        out["message"] = e.user_message
        _log.warning("Gemini 연결 테스트 실패: %s | %s", e.user_message, e.detail)
    except Exception as e:
        out["message"] = "예기치 못한 오류가 났습니다. 서버 터미널의 로그를 확인해 주세요."
        _log.warning("Gemini 연결 테스트 예외: %s: %s", type(e).__name__, str(e)[:120])
    return out

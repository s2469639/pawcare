"""기록 기반 후속 업무 제안.

- 기본: 규칙 기반 '데모 분석'(실제 AI 아님).
- GEMINI_API_KEY + GEMINI_MODEL 이 서버 환경변수에 있으면 Gemini 호출.
- 어떤 경우에도 제안은 DB에 저장하지 않는다. 직원이 승인(업무로 등록)해야 업무가 된다.
- 근거 문장은 반드시 원본 기록에 실제로 있는 문장만 허용한다(없는 사실 생성 방지).
"""
import json
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


def _gemini(record: dict, dog: dict, staff: list[dict], key: str, model: str) -> dict:
    prompt = PROMPT.format(roles=", ".join(s["role"] for s in staff), dog=dog["name"],
                           rtype=record["record_type"], sv=record.get("structured_value") or "-",
                           content=record["content"])
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}},
        timeout=20)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return sanitize_model_output(json.loads(text), record, staff)


def sanitize_model_output(data: dict, record: dict, staff: list[dict]) -> dict:
    """모델 출력 검증: 원문에 없는 근거·금지 표현이 있으면 해당 제안을 버린다."""
    source = (record.get("structured_value") or "") + "\n" + record["content"]
    by_role = {s["role"]: s for s in staff}
    out = []
    for s in (data.get("suggestions") or [])[:3]:
        title, desc = str(s.get("title", "")).strip()[:80], str(s.get("description", "")).strip()[:500]
        ev = [e for e in (s.get("evidence") or []) if isinstance(e, str) and e.strip() and e.strip() in source]
        if not title or not ev or FORBIDDEN.search(title + desc):
            continue
        asg = by_role.get(s.get("assignee_role"))
        out.append({"title": title, "description": desc, "needs_check": True,
                    "assignee_id": asg["id"] if asg else None,
                    "assignee_note": None if asg else "기록에 담당자 정보가 없어 지정이 필요합니다.",
                    "priority": "normal", "evidence": ev})
    facts = [f for f in (data.get("facts") or []) if isinstance(f, str) and f.strip() in source]
    summary = str(data.get("summary", ""))[:300]
    if FORBIDDEN.search(summary):
        summary = ""
    notice = data.get("notice") if isinstance(data.get("notice"), str) else None
    if not out and not notice:
        notice = "기록에서 후속 확인이 필요한 사항이 확인되지 않았습니다."
    return {"summary": summary, "facts": facts, "suggestions": out, "notice": notice}


def suggest(record: dict, dog: dict, staff: list[dict]) -> dict:
    key, model = os.environ.get("GEMINI_API_KEY", "").strip(), os.environ.get("GEMINI_MODEL", "").strip()
    fallback_note = None
    if key and model:
        try:
            res = _gemini(record, dog, staff, key, model)
            res["mode"], res["mode_label"] = "gemini", f"Gemini 분석 ({model})"
            return res
        except Exception:
            fallback_note = "AI 호출에 실패해 데모 분석(규칙 기반)으로 대체했습니다."
    elif key and not model:
        fallback_note = "GEMINI_MODEL이 설정되지 않아 데모 분석(규칙 기반)을 사용했습니다."
    res = demo_analyze(record, staff)
    res["mode"], res["mode_label"] = "demo", "데모 분석 (규칙 기반 · 실제 AI 아님)"
    if fallback_note:
        res["fallback_note"] = fallback_note
    return res

import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..deps import current_staff
from ..schemas import SuggestRequest
from ..services import ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/suggest-tasks")
def suggest_tasks(body: SuggestRequest, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """제안만 반환한다. 저장하지 않으며, 업무 생성은 직원이 POST /api/tasks 로 승인해야 한다."""
    rec = db.execute("SELECT * FROM care_records WHERE id=? AND org_id=?", (body.record_id, staff["org_id"])).fetchone()
    if rec is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    dog = db.execute("SELECT * FROM dogs WHERE id=?", (rec["dog_id"],)).fetchone()
    members = [dict(s) for s in db.execute("SELECT id,name,role FROM staff WHERE org_id=?", (staff["org_id"],))]
    result = ai_service.suggest(dict(rec), dict(dog), members)
    result.update(record_id=rec["id"], dog_id=dog["id"], dog_name=dog["name"])
    for s in result["suggestions"]:
        s["source_record_id"] = rec["id"]
    return result


@router.post("/test")
def test_ai(staff=Depends(current_staff)):
    """AI 설정·연결 점검(직원 전용). 키 값은 응답에 포함하지 않는다."""
    return ai_service.check_connection()


@router.post("/find-models")
def find_models(staff=Depends(current_staff)):
    """내 키로 실제 호출이 되는 모델을 찾는다(직원 전용, 짧은 요청 여러 번 → 무료 한도를 조금 사용)."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "message": "GEMINI_API_KEY가 설정되지 않았습니다.", "working": [], "tried": []}
    try:
        r = ai_service.find_working_models(key)
    except ai_service.AIError as e:
        return {"ok": False, "message": e.user_message, "working": [], "tried": []}
    return {"ok": bool(r["working"]), "message": "" if r["working"] else "호출이 되는 모델을 찾지 못했습니다.", **r}

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

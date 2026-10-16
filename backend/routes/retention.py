"""퇴원한 반려견 목록과 삭제 대상 정리(관리자)."""
import sqlite3

from fastapi import APIRouter, Depends

from .. import retention
from ..database import get_db, now_iso
from ..deps import current_staff
from .common import dog_dict
from .dogs import require_admin

router = APIRouter(prefix="/api/retention", tags=["retention"])


@router.get("/discharged")
def discharged(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """퇴원 처리된 반려견과 삭제 예정일. due=삭제 예정일이 지났고 아직 삭제되지 않음."""
    now = now_iso()
    rows = db.execute("SELECT * FROM dogs WHERE org_id=? AND discharged_at IS NOT NULL ORDER BY purge_after", (staff["org_id"],)).fetchall()
    out = []
    for r in rows:
        d = dog_dict(r)
        out.append({"id": d["id"], "name": d["name"], "discharged_at": d["discharged_at"], "purge_after": d["purge_after"],
                    "purge_days_left": d["purge_days_left"], "purged_at": d["purged_at"],
                    "due": bool(d["purge_after"] and d["purge_after"] <= now and not d["purged_at"])})
    return out


@router.post("/purge")
def purge(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """삭제 예정일이 지난 우리 유치원 반려견의 사진·영상 파일과 보호자 연결을 삭제한다(관리자, 되돌릴 수 없음)."""
    require_admin(staff)
    done = retention.purge_due(db, staff["org_id"])
    return {"purged": done, "count": len(done)}

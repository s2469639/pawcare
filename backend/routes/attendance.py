"""오늘의 출석부. 출석 예정(이용 요일·호텔 숙박·직접 추가) → 출석(등원 시각) → 하원(시각·데려간 사람), 또는 결석.
행이 없는 아이는 '오늘 일정 없음'이다. 등원 체크 없이 기록을 쓰면 자동으로 출석 처리한다(records.py)."""
import sqlite3
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..database import KST, get_db, now_iso
from ..deps import current_staff, get_dog_or_404

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


def today_date() -> date:
    return datetime.now(KST).date()


def parse_days(v) -> list[int]:
    return sorted({int(x) for x in (v or "").split(",") if x.strip().isdigit() and 0 <= int(x) <= 6})


def scheduled_source(dog, day: date) -> Optional[str]:
    """이용 요일 또는 호텔 숙박 기간에 해당하면 'weekday' / 'stay', 아니면 None."""
    if dog["stay_start"] and dog["stay_end"] and date.fromisoformat(dog["stay_start"]) <= day <= date.fromisoformat(dog["stay_end"]):
        return "stay"
    if day.weekday() in parse_days(dog["attend_days"]):
        return "weekday"
    return None


def mark_present(db, org_id: int, dog_id: int, day: str, at: Optional[str] = None) -> None:
    """등원 처리(이미 출석이면 그대로 둔다). 결석·예정 행은 출석으로 바꾼다."""
    row = db.execute("SELECT status FROM attendance WHERE dog_id=? AND day=?", (dog_id, day)).fetchone()
    if row and row["status"] == "present":
        return
    if row:
        db.execute("UPDATE attendance SET status='present', checkin_at=?, absent_note=NULL, absent_contacted=0 WHERE dog_id=? AND day=?", (at or now_iso(), dog_id, day))
    else:
        db.execute("INSERT INTO attendance(org_id,dog_id,day,status,checkin_at,created_at) VALUES (?,?,?,?,?,?)", (org_id, dog_id, day, "present", at or now_iso(), now_iso()))


def present_dog_ids(db, org_id: int, day: str) -> set[int]:
    """이 날 출석한(재원 중) 반려견 id."""
    return {r["dog_id"] for r in db.execute(
        "SELECT a.dog_id FROM attendance a JOIN dogs d ON d.id=a.dog_id WHERE a.org_id=? AND a.day=? AND a.status='present' AND d.attending=1", (org_id, day))}


def day_view(db, org_id: int, day: date) -> dict:
    rows = {r["dog_id"]: r for r in db.execute("SELECT * FROM attendance WHERE org_id=? AND day=?", (org_id, day.isoformat()))}
    dogs = []
    for d in db.execute("SELECT * FROM dogs WHERE org_id=? AND attending=1 ORDER BY id", (org_id,)):
        r, src = rows.get(d["id"]), scheduled_source(d, day)
        if r and r["status"] in ("present", "absent"):
            status = r["status"]
        elif r or src:
            status = "expected"
        else:
            status = None
        source = src or ("manual" if r and r["status"] == "expected" else None)
        dogs.append({"id": d["id"], "name": d["name"], "breed": d["breed"], "photo": d["photo"], "avatar_color": d["avatar_color"],
                     "status": status, "source": source, "attend_days": parse_days(d["attend_days"]),
                     "checkin_at": r["checkin_at"] if r else None, "checkout_at": r["checkout_at"] if r else None,
                     "pickup_by": r["pickup_by"] if r else None, "note": (r["absent_note"] or r["pickup_note"]) if r else None,
                     "absent_contacted": bool(r["absent_contacted"]) if r else False})
    count = lambda s: sum(1 for x in dogs if x["status"] == s)
    return {"date": day.isoformat(), "weekday": "월화수목금토일"[day.weekday()], "dogs": dogs,
            "summary": {"expected": count("expected"), "present": count("present"), "absent": count("absent"), "none": count(None),
                        "checked_out": sum(1 for x in dogs if x["checkout_at"])}}


class CheckoutIn(BaseModel):
    pickup_by: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=200)

    @field_validator("pickup_by", "note")
    @classmethod
    def _strip(cls, v):
        return v.strip()


class AbsentIn(BaseModel):
    contacted: bool = False          # 보호자가 사전에 연락했는지
    note: str = Field(default="", max_length=100)

    @field_validator("note")
    @classmethod
    def _strip(cls, v):
        return v.strip()


def _dog(db, dog_id: int, staff) -> dict:
    d = get_dog_or_404(db, dog_id, staff["org_id"])
    if not d["attending"]:
        raise HTTPException(409, f"{d['name']}은(는) 퇴원 처리되어 출석을 기록할 수 없습니다.")
    return d


def _row(db, dog_id: int):
    return db.execute("SELECT * FROM attendance WHERE dog_id=? AND day=?", (dog_id, today_date().isoformat())).fetchone()


def _one(db, staff, dog_id: int) -> dict:
    return next(x for x in day_view(db, staff["org_id"], today_date())["dogs"] if x["id"] == dog_id)


@router.get("")
def today(staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    return day_view(db, staff["org_id"], today_date())


@router.post("/{dog_id}/checkin")
def checkin(dog_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    _dog(db, dog_id, staff)
    mark_present(db, staff["org_id"], dog_id, today_date().isoformat())
    return _one(db, staff, dog_id)


@router.post("/{dog_id}/checkout")
def checkout(dog_id: int, body: CheckoutIn, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    _dog(db, dog_id, staff)
    r = _row(db, dog_id)
    if r is None or r["status"] != "present":
        raise HTTPException(422, "등원 체크를 한 아이만 하원 처리할 수 있습니다.")
    if r["checkout_at"]:
        raise HTTPException(409, "이미 하원 처리되었습니다.")
    db.execute("UPDATE attendance SET checkout_at=?, pickup_by=?, pickup_note=? WHERE id=?", (now_iso(), body.pickup_by or None, body.note or None, r["id"]))
    return _one(db, staff, dog_id)


@router.post("/{dog_id}/absent")
def absent(dog_id: int, body: AbsentIn, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    _dog(db, dog_id, staff)
    r, day = _row(db, dog_id), today_date().isoformat()
    if r and r["status"] == "present":
        raise HTTPException(422, "이미 등원한 아이는 결석 처리할 수 없습니다. 하원 처리를 사용하세요.")
    if r:
        db.execute("UPDATE attendance SET status='absent', absent_contacted=?, absent_note=? WHERE id=?", (int(body.contacted), body.note or None, r["id"]))
    else:
        db.execute("INSERT INTO attendance(org_id,dog_id,day,status,absent_contacted,absent_note,created_at) VALUES (?,?,?,?,?,?,?)",
                   (staff["org_id"], dog_id, day, "absent", int(body.contacted), body.note or None, now_iso()))
    return _one(db, staff, dog_id)


@router.post("/{dog_id}/add")
def add_today(dog_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """쿠폰제·일일 이용처럼 정해진 요일이 없는 아이를 오늘 출석 예정으로 직접 추가한다."""
    _dog(db, dog_id, staff)
    if _row(db, dog_id) is None:
        db.execute("INSERT INTO attendance(org_id,dog_id,day,status,created_at) VALUES (?,?,?,?,?)", (staff["org_id"], dog_id, today_date().isoformat(), "expected", now_iso()))
    return _one(db, staff, dog_id)


@router.delete("/{dog_id}")
def undo(dog_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """오늘의 출석 기록(등원·하원·결석·직접 추가)을 지워 원래 상태(이용 요일 기준)로 되돌린다."""
    _dog(db, dog_id, staff)
    db.execute("DELETE FROM attendance WHERE dog_id=? AND day=?", (dog_id, today_date().isoformat()))
    return _one(db, staff, dog_id)

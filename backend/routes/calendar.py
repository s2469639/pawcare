"""반 전체 캘린더. 직원은 한 달 일정과 준비 항목을 보고 관리하고, 보호자는 '공개한 일정'과 '보호자 준비물'만 읽는다."""
import calendar as pycal
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..database import KST, get_db, now_iso
from ..deps import current_parent, current_staff

router = APIRouter(prefix="/api", tags=["calendar"])

KINDS = ("program", "event", "closed", "notice")
MAX_SPAN_DAYS = 60
MAX_PREP = 10          # 대상(직원/보호자)별 준비 항목 상한
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _day(v: str) -> date:
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ValueError("날짜 형식이 올바르지 않습니다(YYYY-MM-DD).")


class PrepIn(BaseModel):
    id: Optional[int] = None
    audience: Literal["staff", "parent"]
    text: str = Field(max_length=80)

    @field_validator("text")
    @classmethod
    def _text(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("준비 항목 내용을 입력해 주세요.")
        return v


class EventIn(BaseModel):
    title: str = Field(max_length=60)
    kind: Literal["program", "event", "closed", "notice"]
    start_date: str
    end_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: str = Field(default="", max_length=500)
    parent_visible: bool = False
    prep: Optional[list[PrepIn]] = None

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("일정 제목을 입력해 주세요.")
        return v

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _time_fmt(cls, v):
        if v in (None, ""):
            return None
        if not isinstance(v, str) or not _TIME.match(v):
            raise ValueError("시간 형식이 올바르지 않습니다(HH:MM).")
        return v

    @model_validator(mode="after")
    def _check(self):
        s = _day(self.start_date)
        e = _day(self.end_date or self.start_date)
        if e < s:
            raise ValueError("끝나는 날짜가 시작 날짜보다 빠를 수 없습니다.")
        if (e - s).days >= MAX_SPAN_DAYS:
            raise ValueError(f"일정 기간은 최대 {MAX_SPAN_DAYS}일입니다.")
        self.end_date = e.isoformat()
        if self.end_time and not self.start_time:
            raise ValueError("끝나는 시간만 입력할 수 없습니다. 시작 시간도 입력해 주세요.")
        if self.start_time and self.end_time and s == e and self.end_time <= self.start_time:
            raise ValueError("끝나는 시간이 시작 시간보다 늦어야 합니다.")
        if self.prep is not None:
            for a in ("staff", "parent"):
                if sum(1 for p in self.prep if p.audience == a) > MAX_PREP:
                    raise ValueError(f"준비 항목은 대상별로 최대 {MAX_PREP}개입니다.")
        return self


def _month_range(month: Optional[str]) -> tuple[str, str, str]:
    if month is None:
        month = datetime.now(KST).strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "month는 YYYY-MM 형식이어야 합니다.")
    y, m = int(month[:4]), int(month[5:])
    return month, f"{month}-01", f"{month}-{pycal.monthrange(y, m)[1]:02d}"


def _event(e, prep, staff_view: bool) -> dict:
    d = {"id": e["id"], "title": e["title"], "kind": e["kind"], "start_date": e["start_date"], "end_date": e["end_date"],
         "start_time": e["start_time"], "end_time": e["end_time"], "description": e["description"]}
    if staff_view:
        d["parent_visible"] = bool(e["parent_visible"])
        d["prep"] = [{"id": p["id"], "audience": p["audience"], "text": p["text"], "done": bool(p["done"]),
                      "done_by_name": p["done_by_name"], "done_at": p["done_at"]} for p in prep]
    else:       # 보호자: 보호자용 준비물의 문구만. 직원용 항목과 완료 정보는 내려보내지 않는다
        d["prep"] = [{"text": p["text"]} for p in prep if p["audience"] == "parent"]
    return d


def _load(db, events, staff_view: bool) -> list[dict]:
    ids = [e["id"] for e in events]
    prep: dict[int, list] = {i: [] for i in ids}
    if ids:
        for p in db.execute(
                f"SELECT p.*, s.name AS done_by_name FROM calendar_prep_items p LEFT JOIN staff s ON s.id=p.done_by "
                f"WHERE p.event_id IN ({','.join('?' * len(ids))}) ORDER BY p.sort_order, p.id", ids):
            prep[p["event_id"]].append(p)
    return [_event(e, prep[e["id"]], staff_view) for e in events]


def events_between(db, org_id: int, start: str, end: str, *, staff_view: bool) -> list[dict]:
    """[start, end] 날짜 범위와 겹치는 일정(경계를 걸친 일정 포함)."""
    sql = "SELECT * FROM calendar_events WHERE org_id=? AND start_date<=? AND end_date>=?"
    if not staff_view:
        sql += " AND parent_visible=1"
    return _load(db, db.execute(sql + " ORDER BY start_date, COALESCE(start_time,''), id", (org_id, end, start)).fetchall(), staff_view)


def today_events(db, org_id: int) -> list[dict]:
    t = datetime.now(KST).date().isoformat()
    return events_between(db, org_id, t, t, staff_view=True)


def _get_event(db, event_id: int, org_id: int):
    e = db.execute("SELECT * FROM calendar_events WHERE id=? AND org_id=?", (event_id, org_id)).fetchone()
    if e is None:
        raise HTTPException(404, "일정을 찾을 수 없습니다.")
    return e


def _one(db, event_id: int) -> dict:
    return _load(db, [db.execute("SELECT * FROM calendar_events WHERE id=?", (event_id,)).fetchone()], True)[0]


def _sync_prep(db, event_id: int, items: list[PrepIn]) -> None:
    """전달된 목록으로 준비 항목을 맞춘다: id가 있는 항목은 문구만 고치고(완료 상태 유지), 없는 항목은 추가, 빠진 항목은 삭제."""
    current = {r["id"]: r for r in db.execute("SELECT * FROM calendar_prep_items WHERE event_id=?", (event_id,))}
    keep = set()
    for i, p in enumerate(items):
        if p.id is not None:
            if p.id not in current:
                raise HTTPException(422, "이 일정에 없는 준비 항목입니다.")
            old = current[p.id]
            if old["audience"] != p.audience or old["text"] != p.text:     # 내용이 바뀌면 다시 확인해야 하므로 완료 해제
                db.execute("UPDATE calendar_prep_items SET audience=?, text=?, done=0, done_by=NULL, done_at=NULL, sort_order=? WHERE id=?",
                           (p.audience, p.text, i, p.id))
            else:
                db.execute("UPDATE calendar_prep_items SET sort_order=? WHERE id=?", (i, p.id))
            keep.add(p.id)
        else:
            cur = db.execute("INSERT INTO calendar_prep_items(event_id,audience,text,sort_order) VALUES (?,?,?,?)",
                             (event_id, p.audience, p.text, i))
            keep.add(cur.lastrowid)
    for pid in set(current) - keep:
        db.execute("DELETE FROM calendar_prep_items WHERE id=?", (pid,))


@router.get("/calendar")
def month_view(month: Optional[str] = Query(None), staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    month, start, end = _month_range(month)
    return {"month": month, "events": events_between(db, staff["org_id"], start, end, staff_view=True)}


@router.get("/calendar/upcoming")
def upcoming(days: int = Query(7, ge=1, le=31), staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """오늘부터 N일 안에 겹치는 일정과 아직 끝내지 않은 직원 준비 항목 수."""
    today = datetime.now(KST).date()
    evs = events_between(db, staff["org_id"], today.isoformat(), (today + timedelta(days=days)).isoformat(), staff_view=True)
    for e in evs:
        e["open_prep"] = sum(1 for p in e["prep"] if p["audience"] == "staff" and not p["done"])
    return {"days": days, "events": evs, "open_prep_total": sum(e["open_prep"] for e in evs)}


@router.post("/calendar", status_code=201)
def create_event(body: EventIn, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    now = now_iso()
    cur = db.execute(
        "INSERT INTO calendar_events(org_id,title,kind,start_date,end_date,start_time,end_time,description,parent_visible,created_by,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (staff["org_id"], body.title, body.kind, body.start_date, body.end_date, body.start_time, body.end_time,
         body.description.strip(), int(body.parent_visible), staff["id"], now, now))
    _sync_prep(db, cur.lastrowid, [PrepIn(audience=p.audience, text=p.text) for p in body.prep or []])
    return _one(db, cur.lastrowid)


@router.patch("/calendar/{event_id}")
def update_event(event_id: int, body: EventIn, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """전체 필드를 다시 보내 수정한다. prep을 생략하면 준비 항목은 그대로 둔다."""
    _get_event(db, event_id, staff["org_id"])
    db.execute("UPDATE calendar_events SET title=?, kind=?, start_date=?, end_date=?, start_time=?, end_time=?, description=?, "
               "parent_visible=?, updated_at=? WHERE id=?",
               (body.title, body.kind, body.start_date, body.end_date, body.start_time, body.end_time, body.description.strip(),
                int(body.parent_visible), now_iso(), event_id))
    if body.prep is not None:
        _sync_prep(db, event_id, body.prep)
    return _one(db, event_id)


@router.delete("/calendar/{event_id}")
def delete_event(event_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    _get_event(db, event_id, staff["org_id"])
    db.execute("DELETE FROM calendar_prep_items WHERE event_id=?", (event_id,))
    db.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
    return {"ok": True}


@router.post("/calendar/prep/{item_id}/toggle")
def toggle_prep(item_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    """직원용 준비 항목 체크/해제. 보호자용 항목은 직원이 대신 체크하는 것이 아니므로 체크할 수 없다."""
    p = db.execute("SELECT p.*, e.org_id FROM calendar_prep_items p JOIN calendar_events e ON e.id=p.event_id WHERE p.id=?", (item_id,)).fetchone()
    if p is None or p["org_id"] != staff["org_id"]:
        raise HTTPException(404, "준비 항목을 찾을 수 없습니다.")
    if p["audience"] != "staff":
        raise HTTPException(422, "보호자용 안내 항목은 체크할 수 없습니다.")
    if p["done"]:
        db.execute("UPDATE calendar_prep_items SET done=0, done_by=NULL, done_at=NULL WHERE id=?", (item_id,))
    else:
        db.execute("UPDATE calendar_prep_items SET done=1, done_by=?, done_at=? WHERE id=?", (staff["id"], now_iso(), item_id))
    return _one(db, p["event_id"])


@router.get("/parent/calendar")
def parent_calendar(month: Optional[str] = Query(None), parent=Depends(current_parent), db: sqlite3.Connection = Depends(get_db)):
    """보호자용 월 일정: 같은 유치원이 '보호자 공개'로 둔 일정만, 보호자용 준비물 문구만."""
    month, start, end = _month_range(month)
    return {"month": month, "events": events_between(db, parent["org_id"], start, end, staff_view=False)}

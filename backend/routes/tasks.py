import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db, now_iso
from ..deps import current_staff, get_dog_or_404, get_staff_in_org
from ..schemas import ActionCreate, TaskCreate, TaskPatch
from .common import FILTERS, TASK_SELECT, task_dict

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _log(db, task_id: int, actor_id: int, typ: str, note: Optional[str]):
    db.execute("INSERT INTO task_action_logs(task_id,actor_id,action_type,note,created_at) VALUES (?,?,?,?,?)",
               (task_id, actor_id, typ, note, now_iso()))


def can_act(staff: dict, task: dict) -> bool:
    """확인·조치는 담당자, 관리자, 또는 담당자 미지정 업무에서만 가능(전체 권한 시스템은 범위 밖)."""
    return task["assignee_id"] is None or task["assignee_id"] == staff["id"] or staff["role"] == "관리자"


def _load(db, task_id: int, org_id: int) -> dict:
    r = db.execute(TASK_SELECT + " WHERE t.id=? AND t.org_id=?", (task_id, org_id)).fetchone()
    if r is None:
        raise HTTPException(404, "업무를 찾을 수 없습니다.")
    return task_dict(r)


def _detail(db, task_id: int, org_id: int) -> dict:
    t = _load(db, task_id, org_id)
    t["logs"] = [dict(x) for x in db.execute(
        "SELECT l.*, s.name AS actor_name, s.role AS actor_role FROM task_action_logs l "
        "JOIN staff s ON s.id=l.actor_id WHERE l.task_id=? ORDER BY l.id", (task_id,))]
    return t


@router.get("")
def list_tasks(filter: str = Query("all", pattern="^(all|pending|todo|in_progress|completed)$"),
               dog_id: Optional[int] = None, assignee_id: Optional[int] = None,
               staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    sql, args = TASK_SELECT + " WHERE t.org_id=?", [staff["org_id"]]
    if filter != "all":
        sql += " AND " + FILTERS[filter]
    if dog_id:
        sql += " AND t.dog_id=?"
        args.append(dog_id)
    if assignee_id:
        sql += " AND t.assignee_id=?"
        args.append(assignee_id)
    rows = db.execute(sql + " ORDER BY rank_order, prio_order, t.created_at DESC", args)
    return [task_dict(r) for r in rows]


@router.get("/{task_id}")
def get_task(task_id: int, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    return _detail(db, task_id, staff["org_id"])


@router.post("", status_code=201)
def create_task(body: TaskCreate, staff=Depends(current_staff), db: sqlite3.Connection = Depends(get_db)):
    org = staff["org_id"]
    dog = get_dog_or_404(db, body.dog_id, org)
    if not dog["attending"]:
        raise HTTPException(409, f"{dog['name']}은(는) 퇴원 처리되어 새 업무를 만들 수 없습니다.")
    if body.source_record_id is not None:
        rec = db.execute("SELECT dog_id FROM care_records WHERE id=? AND org_id=?",
                         (body.source_record_id, org)).fetchone()
        if rec is None or rec["dog_id"] != body.dog_id:
            raise HTTPException(422, "원본 기록이 해당 반려견의 기록이 아닙니다.")
    if body.assignee_id is not None:
        get_staff_in_org(db, body.assignee_id, org)
    now = now_iso()
    cur = db.execute(
        "INSERT INTO tasks(org_id,dog_id,source_record_id,title,description,priority,created_by,assignee_id,"
        "created_at,updated_at,ai_suggested) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (org, body.dog_id, body.source_record_id, body.title, body.description, body.priority, staff["id"],
         body.assignee_id, now, now, int(body.ai_suggested)))
    _log(db, cur.lastrowid, staff["id"], "created", "AI 제안을 검토해 등록" if body.ai_suggested else "업무 등록")
    return _detail(db, cur.lastrowid, org)


@router.patch("/{task_id}")
def patch_task(task_id: int, body: TaskPatch, staff=Depends(current_staff),
               db: sqlite3.Connection = Depends(get_db)):
    org = staff["org_id"]
    cur = _load(db, task_id, org)
    if cur["action_status"] == "completed":
        raise HTTPException(409, "완료된 업무는 수정할 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    changes = {}
    if "assignee_id" in data and data["assignee_id"] != cur["assignee_id"]:
        new_name = "미지정"
        if data["assignee_id"] is not None:
            new_name = get_staff_in_org(db, data["assignee_id"], org)["name"]
        changes["assignee_id"] = data["assignee_id"]
        _log(db, task_id, staff["id"], "reassign", f"{cur['assignee_name'] or '미지정'} → {new_name}")
    for k in ("title", "description", "priority"):
        if data.get(k) is not None and data[k] != cur[k]:
            changes[k] = data[k]
    if set(changes) - {"assignee_id"}:
        _log(db, task_id, staff["id"], "edit", "업무 내용 수정")
    if changes:   # 담당자 변경은 확인·조치 상태를 바꾸지 않는다.
        sets = ", ".join(f"{k}=?" for k in changes) + ", updated_at=?"
        db.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*changes.values(), now_iso(), task_id))
    return _detail(db, task_id, org)


@router.post("/{task_id}/actions")
def task_action(task_id: int, body: ActionCreate, staff=Depends(current_staff),
                db: sqlite3.Connection = Depends(get_db)):
    org, now = staff["org_id"], now_iso()
    t = _load(db, task_id, org)
    a = body.action_type
    if a != "comment" and not can_act(staff, t):
        raise HTTPException(403, f"담당자({t['assignee_name']})만 처리할 수 있습니다. 담당자를 변경하거나 해당 직원으로 전환해 주세요.")
    if a == "acknowledge":
        if t["acknowledgment_status"] == "acknowledged":
            raise HTTPException(409, "이미 확인한 업무입니다.")
        db.execute("UPDATE tasks SET acknowledgment_status='acknowledged', acknowledged_by=?, acknowledged_at=?,"
                   " updated_at=? WHERE id=?", (staff["id"], now, now, task_id))
        _log(db, task_id, staff["id"], "acknowledge", body.note or "확인 완료")
    elif a == "start":
        if t["action_status"] != "todo":
            raise HTTPException(409, "조치 필요 상태의 업무만 시작할 수 있습니다.")
        db.execute("UPDATE tasks SET action_status='in_progress', updated_at=? WHERE id=?", (now, task_id))
        _log(db, task_id, staff["id"], "start", body.note or "조치 시작")
    elif a == "complete":
        if t["action_status"] == "completed":
            raise HTTPException(409, "이미 완료된 업무입니다.")
        if not body.note:
            raise HTTPException(422, "조치 결과를 입력해야 완료할 수 있습니다.")
        db.execute("UPDATE tasks SET action_status='completed', completion_note=?, completed_at=?, updated_at=?"
                   " WHERE id=?", (body.note, now, now, task_id))
        _log(db, task_id, staff["id"], "complete", body.note)
    else:  # comment
        if not body.note:
            raise HTTPException(422, "메모 내용을 입력해 주세요.")
        _log(db, task_id, staff["id"], "comment", body.note)
        db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, task_id))
    return _detail(db, task_id, org)

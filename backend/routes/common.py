"""여러 라우트가 공유하는 조회 헬퍼."""
import json
from datetime import date, datetime

from ..database import KST

TASK_SELECT = """
SELECT t.*, d.name AS dog_name, d.avatar_color AS dog_color, d.photo AS dog_photo,
       a.name AS assignee_name, a.role AS assignee_role,
       c.name AS creator_name, c.role AS creator_role,
       k.name AS ack_by_name,
       r.record_type AS src_type, r.content AS src_content, r.observed_at AS src_observed_at,
       CASE WHEN t.action_status='completed' THEN 3
            WHEN t.acknowledgment_status='pending' THEN 0
            WHEN t.action_status='todo' THEN 1 ELSE 2 END AS rank_order,
       CASE t.priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END AS prio_order
FROM tasks t
JOIN dogs d ON d.id=t.dog_id
JOIN staff c ON c.id=t.created_by
LEFT JOIN staff a ON a.id=t.assignee_id
LEFT JOIN staff k ON k.id=t.acknowledged_by
LEFT JOIN care_records r ON r.id=t.source_record_id
"""

FILTERS = {
    "pending": "t.acknowledgment_status='pending' AND t.action_status!='completed'",
    "todo": "t.action_status='todo'",
    "in_progress": "t.action_status='in_progress'",
    "completed": "t.action_status='completed'",
}


def task_dict(r) -> dict:
    d = dict(r)
    d.pop("rank_order", None)
    d.pop("prio_order", None)
    d["ai_suggested"] = bool(d["ai_suggested"])
    return d


def today_prefix() -> str:
    return datetime.now(KST).date().isoformat()


def age_text(birth: str) -> str:
    b = date.fromisoformat(birth)
    t = datetime.now(KST).date()
    months = (t.year - b.year) * 12 + t.month - b.month - (1 if t.day < b.day else 0)
    y, m = divmod(max(months, 0), 12)
    return f"{y}세 {m}개월" if y else f"{m}개월"


def stay_fields(start, end) -> dict:
    """호텔 숙박 기간(입실일~퇴실일)에서 오늘 기준 상태를 계산한다. 기간이 없으면 모두 None."""
    out = {"stay_status": None, "stay_nights": None, "checkin_today": False, "checkout_today": False}
    if not start or not end:
        return out
    s, e, t = date.fromisoformat(start), date.fromisoformat(end), datetime.now(KST).date()
    out.update(stay_nights=(e - s).days, checkin_today=t == s, checkout_today=t == e,
               stay_status="upcoming" if t < s else "ended" if t > e else "checkout_today" if t == e else "staying")
    return out


def dog_dict(r) -> dict:
    d = dict(r)
    d["care_context"] = json.loads(d["care_context"] or "{}")
    d["attending"] = bool(d["attending"])
    d["age_text"] = age_text(d["birth_date"])
    d["discharged"] = bool(d.get("discharged_at"))
    d.update(stay_fields(d.get("stay_start"), d.get("stay_end")))
    d["purge_days_left"] = None
    if d.get("purge_after") and not d.get("purged_at"):
        d["purge_days_left"] = (date.fromisoformat(d["purge_after"][:10]) - datetime.now(KST).date()).days
    return d

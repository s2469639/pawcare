"""여러 라우트가 공유하는 조회 헬퍼."""
import json
from datetime import date, datetime

from ..database import KST

TASK_SELECT = """
SELECT t.*, d.name AS dog_name, d.avatar_color AS dog_color,
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


def dog_dict(r) -> dict:
    d = dict(r)
    d["care_context"] = json.loads(d["care_context"] or "{}")
    d["attending"] = bool(d["attending"])
    d["age_text"] = age_text(d["birth_date"])
    return d

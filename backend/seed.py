"""가상의 샘플 데이터. 모든 이름·정보는 허구입니다."""
import json
import sqlite3
from datetime import datetime, timedelta

from .database import KST, SAMPLE_PHOTOS, TABLES, ensure_routine, init_db, now_iso


def _t(hour: int, minute: int = 0) -> str:
    d = datetime.now(KST).replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=None)
    return d.isoformat()


def reset(conn: sqlite3.Connection) -> None:
    for t in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    init_db(conn)
    seed(conn)


def seed(conn: sqlite3.Connection) -> None:
    c = conn
    c.execute("INSERT INTO organizations(name) VALUES ('해든 도그 유치원'),('달빛 펫호텔')")
    c.executemany(
        "INSERT INTO staff(org_id,name,role) VALUES (?,?,?)",
        [(1, "한지우", "오전 담당자"), (1, "서민재", "오후 담당자"), (1, "정하은", "관리자"), (2, "오하준", "관리자")],
    )

    def ctx(meal="", sensitivity="", behavior="", owner_request="", other=""):
        return json.dumps(
            {"meal": meal, "sensitivity": sensitivity, "behavior": behavior,
             "owner_request": owner_request, "other": other}, ensure_ascii=False)

    dogs = [
        (1, "보리", "푸들", "2022-04-10", "#C98D72", "김서연",
         ctx("건식 사료, 하루 2회 급여", "샘플: 닭고기 간식은 보호자 요청으로 제외", "낯선 소리에 잠시 경계함", "귀가 전 물그릇 확인 요청", "")),
        (1, "두부", "비숑 프리제", "2021-09-02", "#A5AE98", "박도윤",
         ctx("습식 사료 소량 섞어 급여", "", "친구들과 잘 어울림", "", "산책 후 발 닦기")),
        (1, "모카", "말티푸", "2023-01-20", "#8E9A82", "이수아",
         ctx("건식 사료", "", "활동량이 많아 놀이 후 휴식 필요", "알림장에 사진 요청", "")),
        (1, "밤이", "포메라니안", "2020-06-15", "#7C6F64", "최하진",
         ctx("건식 사료, 급여 방식은 보호자 안내 참고", "샘플: 특정 간식 제한(보호자 안내)", "", "급여량 변경 시 먼저 연락 요청", "")),
        (1, "콩이", "믹스견", "2022-11-05", "#B8A58C", "정민호",
         ctx("건식 사료", "", "오후에 활동량이 줄어드는 편(보호자 전달)", "", "")),
        (2, "구름", "골든 리트리버", "2021-03-12", "#A5AE98", "윤재희", ctx("건식 사료", "", "", "", "")),
    ]
    c.executemany(
        "INSERT INTO dogs(org_id,name,breed,birth_date,avatar_color,owner_name,care_context,photo,consent_at) VALUES (?,?,?,?,?,?,?,?,?)",
        [(*d, f"assets/dogs/{SAMPLE_PHOTOS[d[1]]}.webp", now_iso()) for d in dogs])

    def rec(org, dog, author, typ, sv, content, at, status="private", ptext=None, by=None):
        cur = c.execute(
            "INSERT INTO care_records(org_id,dog_id,author_id,record_type,structured_value,content,observed_at,created_at,"
            "parent_status,parent_text,parent_approved_by,parent_approved_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (org, dog, author, typ, sv, content, at, at, status, ptext, by, at if status == "approved" else None))
        return cur.lastrowid

    r_bori_meal = rec(1, 1, 1, "식사", "평소보다 적게 먹음", "점심을 평소보다 적게 먹었습니다.", _t(12, 10))
    r_bori_stool = rec(1, 1, 1, "배변", "평소와 다름", "묽은 변이 관찰되었습니다. 오후 담당자는 다음 배변 상태를 확인해 주세요.", _t(12, 40))
    r_tofu = rec(1, 2, 1, "활동", "직접 입력", "산책 후 물을 마셨습니다.", _t(11, 20))
    rec(1, 3, 1, "활동", "활발함", "놀이 시간에 활발하게 활동했습니다.", _t(10, 30),
        "approved", "놀이 시간에 친구들과 신나게 뛰어놀았어요.", 3)
    r_bam = rec(1, 4, 1, "식사", "직접 입력", "점심 식사 때 급여 방식에 대한 참고사항이 있어 프로필 내용을 다시 확인할 필요가 있습니다.", _t(12, 0))
    r_kong = rec(1, 5, 1, "활동", "활동량이 적음", "오후 활동량 관찰이 필요합니다.", _t(13, 20))
    r_cloud = rec(2, 6, 4, "식사", "잘 먹음", "점심을 잘 먹었습니다.", _t(12, 0))

    def task(org, dog, src, title, desc, creator, assignee, ack, action, created, prio="normal",
             ack_by=None, ack_at=None, note=None, done=None):
        cur = c.execute(
            "INSERT INTO tasks(org_id,dog_id,source_record_id,title,description,priority,created_by,assignee_id,"
            "acknowledgment_status,acknowledged_by,acknowledged_at,action_status,completion_note,created_at,updated_at,completed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (org, dog, src, title, desc, prio, creator, assignee, ack, ack_by, ack_at, action, note, created,
             done or ack_at or created, done))
        tid = cur.lastrowid

        def log(actor, typ, n, at):
            c.execute("INSERT INTO task_action_logs(task_id,actor_id,action_type,note,created_at) VALUES (?,?,?,?,?)",
                      (tid, actor, typ, n, at))
        log(creator, "created", "업무 등록", created)
        if ack == "acknowledged":
            log(ack_by, "acknowledge", "확인 완료", ack_at)
        if action in ("in_progress", "completed"):
            log(assignee, "start", "조치 시작", ack_at or created)
        if action == "completed":
            log(assignee, "complete", note, done)
        return tid

    task(1, 1, r_bori_stool, "오후 배변 상태 확인", "다음 배변 상태를 관찰하고 결과를 기록합니다.",
         1, 2, "pending", "todo", _t(12, 45), prio="high")
    task(1, 4, r_bam, "식사 참고사항 확인", "프로필의 식사 관련 참고사항을 확인하고 저녁 급여 시 반영합니다.",
         1, 2, "acknowledged", "todo", _t(12, 20), ack_by=2, ack_at=_t(13, 0))
    task(1, 5, r_kong, "오후 활동 상태 확인", "오후 활동 상태를 관찰하고 결과를 기록합니다.",
         1, 2, "acknowledged", "in_progress", _t(13, 25), ack_by=2, ack_at=_t(13, 40))
    task(1, 2, r_tofu, "산책 후 음수 기록 확인", "산책 후 물을 마신 내용을 기록에 반영합니다.",
         3, 1, "acknowledged", "completed", _t(11, 30), ack_by=1, ack_at=_t(11, 35),
         note="음수 확인 후 기록에 반영했습니다.", done=_t(11, 50))
    task(2, 6, r_cloud, "식사량 기록 확인", "점심 식사량 기록을 확인합니다.", 4, 4, "pending", "todo", _t(12, 5))
    ensure_routine(c)
    seed_calendar(c)
    seed_accounts(c)
    c.commit()


def seed_calendar(conn: sqlite3.Connection) -> None:
    """반 전체 샘플 일정(오늘 기준 상대 날짜). 샘플 유치원(첫 번째 유치원)에만 채운다."""
    org = conn.execute("SELECT o.id, (SELECT id FROM staff WHERE org_id=o.id AND role='관리자' LIMIT 1) AS admin FROM organizations o "
                       "WHERE o.name='해든 도그 유치원'").fetchone()
    if org is None or org["admin"] is None or conn.execute("SELECT 1 FROM calendar_events WHERE org_id=?", (org["id"],)).fetchone():
        return
    today = datetime.now(KST).date()
    d = lambda n: (today + timedelta(days=n)).isoformat()
    now = now_iso()
    # (제목, 종류, 시작, 끝, 시작시간, 끝시간, 설명, 보호자 공개, [(대상, 준비 항목)])
    events = [
        ("가을 소풍 산책", "event", d(3), d(3), "10:00", "12:00", "근처 공원에서 반 전체가 함께 산책합니다. 날씨가 나쁘면 실내 놀이로 바뀝니다.", 1,
         [("staff", "산책 코스 사전 확인"), ("staff", "여분 리드줄·배변봉투 챙기기"), ("staff", "참가 동의 확인"), ("parent", "편한 하네스 착용"), ("parent", "전날 밤 충분한 휴식")]),
        ("정기 예방접종 확인 주간", "notice", d(5), d(9), None, None, "접종 증명서가 만료되는 아이는 새 증명서를 가져와 주세요.", 1,
         [("staff", "접종 만료 임박 아이 명단 정리"), ("parent", "접종 증명서 사진 또는 원본 지참")]),
        ("직원 교육의 날(오후 휴무)", "closed", d(8), d(8), "13:00", "20:00", "직원 교육으로 오후 운영을 쉽니다. 오전 등원은 정상 운영합니다.", 1,
         [("parent", "오후 하원 시간을 12시 30분까지로 조정")]),
        ("내부 시설 점검", "notice", d(10), d(10), None, None, "놀이방 바닥 점검. 직원만 확인하는 일정입니다.", 0,
         [("staff", "점검 업체 출입 확인"), ("staff", "점검 시간 동안 아이들 이동 장소 정하기")]),
        ("할로윈 변장 놀이", "program", d(14), d(14), "14:00", "16:00", "간단한 소품으로 변장하고 사진을 남깁니다.", 1,
         [("staff", "소품 안전 점검(삼킬 수 있는 장식 제외)"), ("parent", "변장을 싫어하는 아이는 미리 알려주세요")]),
    ]
    for title, kind, s, e, st, et, desc, vis, prep in events:
        cur = conn.execute("INSERT INTO calendar_events(org_id,title,kind,start_date,end_date,start_time,end_time,description,parent_visible,"
                           "created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           (org["id"], title, kind, s, e, st, et, desc, vis, org["admin"], now, now))
        conn.executemany("INSERT INTO calendar_prep_items(event_id,audience,text,sort_order) VALUES (?,?,?,?)",
                         [(cur.lastrowid, a, t, i) for i, (a, t) in enumerate(prep)])


# 데모 계정(가상): 이름 → 이메일. 모두 같은 공개 비밀번호를 쓰므로 인터넷 공개 배포에는 사용하지 않는다.
DEMO_EMAILS = {"한지우": "jiwoo.han", "서민재": "minjae.seo", "정하은": "haeun.jung", "오하준": "hajun.oh",
               "김서연": "seoyeon.kim", "박도윤": "doyun.park", "이수아": "sua.lee"}
DEMO_PARENT_DOGS = ("보리", "두부", "모카")     # 이 반려견의 보호자만 데모 계정을 만들고, 나머지는 초대 코드 시연용으로 비워 둔다


def seed_accounts(conn: sqlite3.Connection) -> None:
    """계정이 하나도 없을 때만 샘플 직원·보호자의 데모 계정을 만든다(멱등)."""
    from . import auth
    if conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() or not conn.execute("SELECT 1 FROM staff LIMIT 1").fetchone():
        return
    pw = auth.hash_password(auth.demo_password())      # 데모 계정은 해시를 공유해 시드 시간을 줄인다
    for s in conn.execute("SELECT * FROM staff ORDER BY id").fetchall():
        local = DEMO_EMAILS.get(s["name"]) or f"staff{s['id']}"
        email = f"{local}@pawcare.demo"
        conn.execute("INSERT INTO accounts(org_id,email,name,password_hash,role,staff_id,is_demo,created_at) VALUES (?,?,?,?,?,?,1,?)",
                     (s["org_id"], email, s["name"], pw, "staff", s["id"], now_iso()))
    for d in conn.execute("SELECT * FROM dogs ORDER BY id").fetchall():
        if d["name"] in DEMO_PARENT_DOGS and d["owner_name"] in DEMO_EMAILS:
            cur = conn.execute("INSERT INTO accounts(org_id,email,name,password_hash,role,is_demo,created_at) VALUES (?,?,?,?,?,1,?)",
                               (d["org_id"], f"{DEMO_EMAILS[d['owner_name']]}@pawcare.demo", d["owner_name"], pw, "parent", now_iso()))
            conn.execute("INSERT INTO guardian_dogs(account_id,dog_id) VALUES (?,?)", (cur.lastrowid, d["id"]))

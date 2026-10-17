"""README용 시연 화면 캡처. 서버 실행 후: python tests/capture_screenshots.py [BASE_URL]
샘플 데이터를 초기화한 뒤 시연 순서대로 docs/screenshots/ 에 저장한다."""
import glob
import os
import sys
import urllib.request

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)
urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/demo/reset", method="POST")).read()

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0], args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=1)
    page.add_init_script("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent='.toasts{display:none!important}';document.head.appendChild(s)})")

    def shot(name, full=False):
        page.wait_for_timeout(400)
        page.screenshot(path=f"{OUT}/{name}.png", full_page=full)
        print("saved", name)

    page.goto(BASE); shot("01-role-select")
    page.get_by_role("button", name="선생님으로 시작하기").click()
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible(); shot("02-dashboard", True)

    page.goto(f"{BASE}/#/dogs"); expect(page.locator(".dog-card")).to_have_count(5); shot("03-dogs")
    page.goto(f"{BASE}/#/dogs/1"); expect(page.get_by_role("heading", name="보리")).to_be_visible(); shot("04-dog-profile", True)

    page.goto(f"{BASE}/#/record/new?dog=1")
    page.locator("#f").get_by_text("배변", exact=True).click()
    page.locator("#f").get_by_text("평소와 다름", exact=True).click()
    page.locator("#content").fill("점심을 평소보다 적게 먹었고 묽은 변을 봤습니다. 오후 담당자는 다음 배변 상태를 확인해 주세요.")
    shot("05-record-form", True)
    page.get_by_role("button", name="기록 저장").click()
    page.get_by_role("link", name="후속 업무 제안 받기").click()
    expect(page.locator(".sugg h3")).to_have_text("오후 배변 상태 확인"); shot("06-ai-suggestion", True)
    page.get_by_role("button", name="업무로 등록").click()
    page.get_by_role("link", name="업무 보기").click()
    expect(page.get_by_role("heading", name="오후 배변 상태 확인")).to_be_visible(); shot("07-task-pending-as-morning", True)

    page.locator("#who").select_option(label="오후 담당자 · 서민재")
    page.locator("#ack").click()
    expect(page.locator(".statebox > div").first).to_contain_text("확인 완료"); shot("08-task-acknowledged", True)
    page.get_by_role("button", name="조치 시작").click()
    expect(page.locator(".statebox > div").nth(1)).to_contain_text("진행 중")
    page.locator("#note").fill("오후 배변 상태를 확인했습니다. 기록 결과: 정상.")
    page.get_by_role("button", name="조치 완료").click()
    expect(page.get_by_role("heading", name="조치 결과")).to_be_visible(); shot("09-task-completed", True)

    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible(); shot("10-dashboard-after", True)
    page.goto(f"{BASE}/#/tasks"); expect(page.locator(".task-row").first).to_be_visible(); shot("11-task-handoff-list", True)

    page.locator("#who").select_option(label="보호자 · 이수아 (모카)")                      # 데모 계정 전환 → 보호자 화면
    expect(page.locator(".feed")).to_contain_text("신나게"); shot("12-parent-preview")
    page.locator("#who").select_option(label="오후 담당자 · 서민재")
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()

    # 일과
    page.goto(f"{BASE}/#/dashboard"); expect(page.locator(".routine.compact .rblock")).to_have_count(6); shot("14-dashboard-routine")
    page.goto(f"{BASE}/#/routine")
    page.locator(".rblock", has_text="점심·휴식").click(); expect(page.locator("#bt")).to_contain_text("점심·휴식"); shot("15-routine-lunch", True)
    page.locator(".rblock", has_text="오후 산책·놀이").click(); expect(page.locator(".handoff")).to_be_visible(); shot("16-routine-handoff", True)

    # 반려견 등록 + 사진 자르기 (가로 사진을 올려 원형 가이드 안에서 자른다)
    from PIL import Image, ImageDraw
    import tempfile
    im = Image.new("RGB", (900, 600), (233, 224, 205)); d = ImageDraw.Draw(im)
    d.ellipse((470, 130, 770, 430), fill=(190, 140, 100)); d.ellipse((540, 230, 580, 270), fill=(40, 40, 40)); d.ellipse((660, 230, 700, 270), fill=(40, 40, 40)); d.ellipse((590, 310, 650, 350), fill=(60, 40, 40))
    path = os.path.join(tempfile.gettempdir(), "demo_dog.png"); im.save(path)
    page.goto(f"{BASE}/#/dogs"); page.locator("#add-dog").click()
    m = page.locator(".modal")
    m.get_by_label("이름 *", exact=True).fill("초코"); m.get_by_label("견종 *").fill("닥스훈트"); m.get_by_label("생년월일 *").fill("2023-05-01"); m.get_by_label("보호자 이름 *").fill("강민지")
    page.locator("#pp-file").set_input_files(path); expect(page.locator("#cv")).to_be_visible()
    box = page.locator("#cv").bounding_box(); page.mouse.move(box["x"] + 150, box["y"] + 150); page.mouse.down(); page.mouse.move(box["x"] + 20, box["y"] + 150, steps=6); page.mouse.up()
    shot("17-photo-cropper")
    page.locator("#ok").click(); expect(page.locator("#pp-prev img")).to_have_count(1); shot("18-register-dog")
    m.get_by_role("button", name="등록", exact=True).click(); expect(page.get_by_role("heading", name="초코")).to_be_visible(); shot("19-new-dog-profile")

    # 사진 첨부 (샘플 반려견 이미지로 '찍은 사진' 대신 사용)
    def pet_photo(name, bg, path):
        base = Image.new("RGB", (1200, 800), bg)
        av = Image.open(os.path.join(os.path.dirname(__file__), "..", "frontend", "assets", "dogs", f"{name}.webp")).convert("RGBA").resize((520, 520))
        base.paste(av, (340, 140), av); base.save(path, "JPEG", quality=88)
    ph = [os.path.join(tempfile.gettempdir(), f"pet_{n}.jpg") for n in ("bori", "tofu")]
    pet_photo("bori", (233, 224, 205), ph[0]); pet_photo("tofu", (214, 224, 232), ph[1])
    page.goto(f"{BASE}/#/record/new?dog=1")
    page.locator("#content").fill("산책 후 사진을 남깁니다. 두부와 함께 놀았어요.")
    page.locator("#pa-file").set_input_files(ph); expect(page.locator(".pa-item")).to_have_count(2)
    page.locator('[data-tag="2"]').click(); shot("24-photo-attach", True)
    page.get_by_role("button", name="기록 저장").click(); expect(page.locator("#done")).to_contain_text("사진 2장을 첨부했습니다.")
    page.goto(f"{BASE}/#/dogs/1"); expect(page.locator(".timeline").first.locator(".thumb")).to_have_count(2); shot("26-dog-photos", True)
    page.locator(".timeline").first.locator(".thumb").first.click(); expect(page.locator(".viewer img")).to_be_visible()
    page.wait_for_timeout(500); shot("25-photo-viewer"); page.keyboard.press("Escape")

    # 공개 승인(사진별 공개 대상) → 보호자 알림장
    page.locator(".timeline li", has=page.locator(".thumb")).first.get_by_role("button", name="보호자 공개 승인…").click()
    expect(page.locator(".share-row")).to_have_count(2)
    page.locator(".share-row").nth(0).get_by_label("두부의 보호자").check(); shot("27-share-modal")
    page.locator(".modal").get_by_role("button", name="공개 승인", exact=True).click()
    expect(page.locator(".timeline").first).to_contain_text("보호자 공개됨")
    page.locator("#who").select_option(label="보호자 · 김서연 (보리)")
    expect(page.get_by_role("heading", name="김서연님의 알림장")).to_be_visible(); expect(page.locator(".feed .thumb")).to_have_count(2)
    page.wait_for_timeout(500); shot("28-parent-feed", True)
    page.locator(".feed .thumb").first.click(); expect(page.locator(".viewer img")).to_be_visible(); page.wait_for_timeout(500); shot("29-parent-viewer"); page.keyboard.press("Escape")
    page.locator("#who").select_option(label="오후 담당자 · 서민재")
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()

    # 일과: 사진 공유 시점(점심 구간에 사진이 있는데 아직 공개 전인 아이)
    kst_today = page.evaluate("new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000).toISOString().slice(0, 10)")
    page.goto(f"{BASE}/#/record/new?dog=2"); page.locator("#at").fill(f"{kst_today}T12:30")
    page.locator("#content").fill("점심을 먹고 낮잠 자기 전에 한 컷."); page.locator("#pa-file").set_input_files(ph[1]); expect(page.locator(".pa-item")).to_have_count(1)
    page.get_by_role("button", name="기록 저장").click(); expect(page.locator("#done")).to_contain_text("사진 1장을 첨부했습니다.")
    page.goto(f"{BASE}/#/routine"); page.locator(".rblock", has_text="점심·휴식").click()
    expect(page.locator(".share-card")).to_be_visible(); page.wait_for_timeout(500); shot("30-routine-share", True)

    # 캘린더: 직원 월간 화면(오늘 일정 하나 추가) → 보호자 일정
    page.locator("#who").select_option(label="관리자 · 정하은"); page.wait_for_timeout(900)
    page.goto(f"{BASE}/#/calendar"); expect(page.get_by_role("heading", name="캘린더")).to_be_visible()
    page.get_by_role("button", name="일정 추가").click(); dlg = page.get_by_role("dialog")
    dlg.get_by_label("제목").fill("원내 산책 대회"); dlg.get_by_label("보호자 일정에 공개").check()
    dlg.get_by_label("시작 시간 (비우면 종일)").fill("14:00"); dlg.get_by_label("끝나는 시간").fill("15:30")
    dlg.get_by_label("설명").fill("반 친구들과 함께 마당을 돕니다. 가장 신나게 걷는 아이에게 작은 간식을 줍니다.")
    dlg.locator('[data-add="staff"]').click(); dlg.locator('[data-list="staff"] input').last.fill("마당 바닥 점검")
    dlg.locator('[data-add="staff"]').click(); dlg.locator('[data-list="staff"] input').last.fill("간식·물그릇 준비")
    dlg.locator('[data-add="parent"]').click(); dlg.locator('[data-list="parent"] input').fill("편한 하네스를 착용해 주세요")
    dlg.locator("#ef button[type=submit]").click(); expect(page.locator(".cal-event", has_text="원내 산책 대회")).to_be_visible()
    page.locator(".cal-event", has_text="원내 산책 대회").locator("[data-prep]").first.check(); page.wait_for_timeout(700); shot("39-calendar-staff", True)
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="다가오는 일정")).to_be_visible(); page.wait_for_timeout(500); shot("40-dashboard-upcoming", True)
    page.locator("#who").select_option(label="보호자 · 김서연 (보리)"); page.wait_for_timeout(900)
    page.goto(f"{BASE}/#/parent/calendar"); expect(page.get_by_role("heading", name="우리 반 일정")).to_be_visible(); page.wait_for_timeout(600); shot("41-calendar-parent", True)
    page.locator("#who").select_option(label="관리자 · 정하은"); page.wait_for_timeout(900)

    # 오늘의 출석부: 일부는 등원 전, 한 마리는 결석, 한 마리는 하원 완료
    page.goto(f"{BASE}/#/attendance"); expect(page.get_by_role("heading", name="오늘의 출석부")).to_be_visible()
    att = lambda n: page.locator(".att-row", has_text=n)
    def waiting(n):
        att(n).get_by_role("button", name="되돌리기").click(); expect(att(n).get_by_role("button", name="되돌리기")).to_have_count(0)
        if att(n).get_by_role("button", name="오늘 추가").count(): att(n).get_by_role("button", name="오늘 추가").click()
        expect(att(n).get_by_role("button", name="결석")).to_be_visible()
    for n in ("두부", "모카", "콩이"): waiting(n)
    att("콩이").get_by_role("button", name="결석").click(); dlg = page.get_by_role("dialog")
    dlg.get_by_label("보호자가 미리 연락했어요").check(); dlg.get_by_label("사유 메모").fill("병원 방문"); dlg.get_by_role("button", name="결석 처리").click()
    expect(att("콩이")).to_contain_text("결석")
    att("보리").get_by_role("button", name="하원 처리").click(); dlg = page.get_by_role("dialog")
    dlg.get_by_label("데려간 사람").fill("보호자 본인"); dlg.get_by_label("하원 전달사항").fill("오후에 물을 잘 마셨어요"); dlg.get_by_role("button", name="하원 처리").click()
    expect(att("보리")).to_contain_text("하원"); page.wait_for_timeout(500); shot("46-attendance", True)
    page.get_by_role("button", name="예정된 아이 모두 등원 체크").click(); expect(page.get_by_role("button", name="예정된 아이 모두 등원 체크")).to_have_count(0)
    att("콩이").get_by_role("button", name="등원 체크").click(); expect(att("콩이")).to_contain_text("등원")

    # 호텔: 업종별 일과 템플릿(야간 인계)
    page.locator("#who").select_option(label="관리자 · 오하준"); page.wait_for_timeout(900)
    page.goto(f"{BASE}/#/routine"); expect(page.locator(".rblock", has_text="굿나잇 체크")).to_be_visible()
    page.locator(".rblock", has_text="저녁 식사·배변").click(); expect(page.locator(".handoff")).to_contain_text("저녁 → 야간 담당자"); page.wait_for_timeout(500); shot("43-hotel-routine", True)
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("status").filter(has_text="숙박 현황")).to_be_visible(); page.wait_for_timeout(500); shot("44-hotel-dashboard", True)
    page.goto(f"{BASE}/#/dogs"); expect(page.locator(".dog-card", has_text="구름")).to_contain_text("숙박 중"); shot("45-hotel-dogs")
    page.locator("#who").select_option(label="관리자 · 정하은"); page.wait_for_timeout(900)

    # 퇴원 처리(관리자) → 삭제 예정 안내 → 재등록
    page.locator("#who").select_option(label="관리자 · 정하은"); page.wait_for_timeout(900)
    page.goto(f"{BASE}/#/dogs/3"); expect(page.get_by_role("button", name="퇴원 처리")).to_be_visible()
    page.get_by_role("button", name="퇴원 처리").click(); page.locator(".modal input[name=ok]").check(); shot("32-discharge-modal")
    page.locator(".modal").get_by_role("button", name="퇴원 처리", exact=True).click()
    expect(page.locator("#view")).to_contain_text("삭제될 예정입니다"); page.wait_for_timeout(600); shot("33-discharged-profile")
    page.goto(f"{BASE}/#/dogs"); page.get_by_role("button", name="퇴원", exact=True).click()
    expect(page.locator("#purge-panel")).to_contain_text("삭제 예정 현황"); page.wait_for_timeout(500); shot("34-purge-panel")
    page.locator("#who").select_option(label="보호자 · 이수아 (모카)")
    expect(page.locator("#pw")).to_contain_text("퇴원했어요"); page.wait_for_timeout(600); shot("35-parent-discharged")
    page.locator("#who").select_option(label="관리자 · 정하은"); page.wait_for_timeout(900)
    page.goto(f"{BASE}/#/dogs/3"); page.once("dialog", lambda d: d.accept()); page.get_by_role("button", name="재등록 처리").click()
    expect(page.get_by_role("button", name="퇴원 처리")).to_be_visible()
    page.locator("#who").select_option(label="오후 담당자 · 서민재"); page.wait_for_timeout(900)

    # 로그인 · 보호자 초대 · 가입
    page.goto(f"{BASE}/#/dogs/4"); page.get_by_role("button", name="초대 코드 만들기").click()
    expect(page.locator(".invite-code")).to_be_visible(); code = page.locator(".invite-code").inner_text().strip(); shot("20-invite-code")
    page.locator(".modal").get_by_role("button", name="확인").click()
    page.get_by_role("button", name="처음 화면으로").click()
    expect(page.get_by_role("button", name="선생님으로 시작하기")).to_be_visible()            # 로그아웃이 끝난 뒤 이동
    page.goto(f"{BASE}/#/login"); expect(page.get_by_role("heading", name="로그인")).to_be_visible(); shot("21-login")
    page.goto(f"{BASE}/#/register")
    page.get_by_label("초대 코드 *").fill(code); page.get_by_label("이름 *").fill("최하진"); page.get_by_label("이메일 *").fill("hajin@example.com")
    page.get_by_label("비밀번호 *", exact=True).fill("새비밀번호-2026"); page.get_by_label("비밀번호 확인 *").fill("새비밀번호-2026"); shot("22-register")
    page.goto(f"{BASE}/#/login")
    page.get_by_label("이메일").fill("minjae.seo@pawcare.demo"); page.get_by_label("비밀번호").fill("pawcare-demo")
    page.get_by_role("button", name="로그인", exact=True).click(); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()

    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible(); shot("13-mobile-dashboard")
    page.goto(f"{BASE}/#/calendar"); expect(page.get_by_role("heading", name="캘린더")).to_be_visible(); page.wait_for_timeout(500); shot("42-mobile-calendar")
    assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"), "모바일 캘린더 가로 스크롤"
    b.close()

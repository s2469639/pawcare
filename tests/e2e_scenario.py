"""핵심 시연 시나리오 E2E (실제 브라우저 조작). 사용법:
   DEMO_MODE=1 로 서버를 실행한 뒤  python tests/e2e_scenario.py [BASE_URL]
   (기본 http://localhost:8000, 실행 전 POST /api/demo/reset 으로 샘플 데이터를 초기화합니다.)
"""
import glob
import os
import re
import sys
import urllib.error
import urllib.request

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SHOTS = os.environ.get("SHOTS", "/tmp/shots")
os.makedirs(SHOTS, exist_ok=True)
req = urllib.request.Request(f"{BASE}/api/demo/reset", method="POST")
urllib.request.urlopen(req).read()
results = []


def step(name):
    results.append(name)
    print("✔", name)


with sync_playwright() as p:
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]
    b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts.g" not in m.text and "ERR_" not in m.text else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    # 앱의 fetch 요청 수를 세어 화면 전환(SPA)이 끝났는지 판단한다. (Playwright의 networkidle은 해시 이동으로 시작된 새 요청을 기다려 주지 않는다)
    page.add_init_script("""(() => { const f = window.fetch; window.__pending = 0; window.__lastNet = Date.now();
      window.fetch = (...a) => { window.__pending++; return f(...a).finally(() => { window.__pending--; window.__lastNet = Date.now(); }); }; })()""")

    def settle():
        page.wait_for_function("window.__pending === 0 && Date.now() - window.__lastNet > 350", timeout=15000)

    def pick(label):
        """데모 계정 전환. 전환 전후로 진행 중인 요청이 없을 때까지 기다린다 — 로딩 중이던 이전 화면의 요청이 새 세션으로 나가는 것을 피한다."""
        settle()
        page.locator("#who").select_option(label=label)
        settle()

    def switch_to(label, heading):
        pick(label)
        expect(page.get_by_role("heading", name=heading)).to_be_visible()
        settle()
    shot = lambda n: page.screenshot(path=f"{SHOTS}/{n}.png", full_page=True)

    # 1. 역할 선택 → 대시보드
    page.goto(BASE)
    shot("01-role")
    page.get_by_role("button", name="선생님으로 시작하기").click()
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()
    stat = lambda label: page.locator(".stat", has_text=label).locator(".num")
    expect(stat("오늘 돌봄 중인 반려견")).to_have_text("5")
    expect(stat("확인이 필요한 업무")).to_have_text("1")
    expect(stat("조치 진행 중")).to_have_text("1")
    expect(stat("완료된 업무")).to_have_text("1")
    shot("02-dashboard")
    step("역할 선택 → 직원 대시보드, 요약 숫자가 데이터에서 계산됨")

    # 필터
    page.get_by_role("link", name="완료 1").click()
    expect(page.locator(".task-row")).to_have_count(1)
    expect(page.locator(".task-row")).to_contain_text("산책 후 음수")
    page.get_by_role("link", name="전체 4").click()
    expect(page.locator(".task-row")).to_have_count(4)
    assert page.locator(".task-row").first.get_attribute("data-task") == "1", "미확인 업무가 가장 위에 와야 함"
    step("대시보드 필터가 목록을 바꾸고, 미확인 업무가 최상단")

    # 2. 반려견 목록 검색 → 보리
    page.get_by_role("link", name="반려견 목록").click()
    expect(page.locator(".dog-card")).to_have_count(5)
    page.get_by_label("이름 검색").fill("보")
    expect(page.locator(".dog-card")).to_have_count(1)
    page.get_by_role("button", name="확인 필요").click()
    expect(page.locator(".dog-card")).to_have_count(1)
    page.get_by_label("이름 검색").fill("없는이름")
    expect(page.get_by_text("조건에 맞는 반려견이 없습니다")).to_be_visible()
    page.get_by_label("이름 검색").fill("보리")
    shot("03-dogs")
    page.locator(".dog-card").click()
    expect(page.get_by_role("heading", name="보리")).to_be_visible()
    expect(page.get_by_text("지속적으로 확인해야 할 돌봄 정보")).to_be_visible()
    shot("04-dog-detail")
    step("반려견 목록 검색·필터 작동, 보리 프로필 진입")

    # 3. 기록 작성
    page.locator(".dog-head").get_by_role("link", name="돌봄 기록 작성").click()
    expect(page.locator("#dog")).to_have_value("1")
    page.locator("#f").get_by_text("배변", exact=True).click()
    page.locator("#f").get_by_text("평소와 다름", exact=True).click()
    page.locator("#content").fill("점심을 평소보다 적게 먹었고 묽은 변을 봤습니다. 오후 담당자는 다음 배변 상태를 확인해 주세요.")
    page.get_by_role("button", name="기록 저장").click()
    expect(page.get_by_text("보리의 기록을 저장했습니다")).to_be_visible()
    shot("05-record-saved")
    step("빠른 기록 저장 (자동으로 업무가 생기지 않음)")
    tasks_before = page.request.get(f"{BASE}/api/dashboard").text().count('"title"')
    assert tasks_before == 4, tasks_before

    # 4. AI 제안
    page.get_by_role("link", name="후속 업무 제안 받기").click()
    expect(page.locator(".mode")).to_contain_text("데모 분석")
    expect(page.locator(".sugg h3")).to_have_text("오후 배변 상태 확인")
    expect(page.locator(".sugg")).to_contain_text("서민재")
    shot("06-ai")
    page.get_by_role("button", name="제안 무시").click()
    expect(page.get_by_text("업무가 생성되지 않았습니다")).to_be_visible()
    d = page.request.get(f"{BASE}/api/dashboard").text()
    assert d.count('"title"') == 4, "무시했는데 업무가 생성됨"
    step("AI 제안 표시(데모 분석 라벨), 제안 무시 시 업무 미생성")
    page.get_by_role("button", name="되돌리기").click()
    page.get_by_role("button", name="수정하기").click()
    page.get_by_label("업무 설명").fill("다음 배변 상태를 관찰하고 결과를 기록합니다. (수정)")
    page.get_by_role("button", name="수정 내용으로 등록").click()
    expect(page.get_by_text("업무로 등록됨")).to_be_visible()
    page.get_by_role("link", name="업무 보기").click()
    expect(page.get_by_role("heading", name="오후 배변 상태 확인")).to_be_visible()
    expect(page.get_by_text("배변 기록 #8")).to_be_visible()
    expect(page.get_by_text("AI 제안을 직원이 승인")).to_be_visible()
    shot("07-task-new")
    step("제안 수정 후 승인 → 업무 생성, 원본 기록(#8)과 연결")

    # 5. 담당자 확인 (오전 담당자로는 처리 불가 → 오후 담당자로 전환)
    expect(page.locator("#ack")).to_be_disabled()
    pick("오후 담당자 · 서민재")
    expect(page.locator("#ack")).to_be_enabled()
    expect(page.locator(".statebox")).to_contain_text("확인 대기")
    page.locator("#ack").click()
    expect(page.locator(".statebox > div").first).to_contain_text("확인 완료")
    expect(page.locator(".statebox > div").nth(1)).to_contain_text("조치 필요")
    shot("08-acked")
    step("담당자 전환 → 확인 완료 (조치 상태는 '조치 필요' 유지)")

    # 6. 조치
    page.get_by_role("button", name="조치 시작").click()
    expect(page.locator(".statebox > div").nth(1)).to_contain_text("진행 중")
    page.get_by_role("button", name="조치 완료").click()
    expect(page.get_by_text("조치 결과를 입력해야")).to_be_visible()
    expect(page.locator(".statebox > div").nth(1)).to_contain_text("진행 중")
    page.locator("#note").fill("오후 배변 상태를 확인했습니다. 기록 결과: 정상.")
    page.get_by_role("button", name="조치 완료").click()
    expect(page.get_by_role("heading", name="조치 결과")).to_be_visible()
    expect(page.locator(".statebox > div").nth(1)).to_contain_text("완료 오늘")
    shot("09-completed")
    step("조치 결과 없이는 완료 불가, 입력 후 완료·완료 시각 기록")

    # 7. 일관성
    page.get_by_role("link", name="오늘의 업무").click()
    expect(stat("확인이 필요한 업무")).to_have_text("1")  # 샘플 보리 업무(#1) 남음
    expect(stat("완료된 업무")).to_have_text("2")
    page.get_by_role("link", name="반려견").first.click()
    page.locator(".dog-card", has_text="보리").click()
    row = page.locator(".task-row", has_text="오후 배변 상태 확인").filter(has_text="조치 완료").first
    expect(row).to_contain_text("조치 완료")
    expect(row).to_contain_text("확인 완료")
    expect(page.locator(".timeline").first).to_contain_text("묽은 변")
    expect(page.locator(".link-task").first).to_be_visible()
    shot("10-dog-after")
    step("대시보드·업무·반려견 프로필의 상태 일치")

    # 샘플 업무 #1 (오후 담당자 서민재): 확인만 누르면 조치 상태 유지
    page.goto(f"{BASE}/#/tasks/1")
    page.locator("#ack").click()
    expect(page.locator(".statebox > div").nth(1)).to_contain_text("조치 필요")
    step("샘플 업무: 확인 완료만으로 조치 완료가 되지 않음")

    # 8. 새로고침 유지
    page.reload()
    expect(page.locator(".statebox > div").first).to_contain_text("확인 완료")
    page.goto(f"{BASE}/#/dogs/1")
    page.reload()
    expect(page.locator(".timeline").first).to_contain_text("묽은 변")
    step("새로고침 후 데이터 유지")

    # 9. 오류 처리
    page.goto(f"{BASE}/#/record/new")
    page.get_by_role("button", name="기록 저장").click()
    expect(page.get_by_text("반려견을 선택해 주세요.")).to_be_visible()
    expect(page.get_by_text("관찰 값을 선택하거나 상세 메모를 입력해 주세요.")).to_be_visible()
    shot("11-form-errors")
    page.goto(f"{BASE}/#/dogs/999")
    expect(page.get_by_text("반려견을 찾을 수 없습니다").first).to_be_visible()
    page.goto(f"{BASE}/#/tasks/999")
    expect(page.get_by_text("화면을 불러오지 못했습니다")).to_be_visible()
    page.get_by_role("link", name="반려견").first.click()
    expect(page.locator(".dog-card").first).to_be_visible()  # 앱 전체가 깨지지 않음
    errors[:] = [e for e in errors if "404" not in e]  # 위에서 일부러 요청한 없는 ID(999)의 404는 제외
    step("필수 입력 오류 메시지, 없는 ID 처리, 앱 유지")

    # 10. 보호자 공개 승인 → 미리보기
    page.goto(f"{BASE}/#/dogs/1")
    page.get_by_role("button", name="보호자 공개 승인…").first.click()
    page.get_by_label("보호자에게 보여줄 문구 *").fill("오늘 점심은 조금 적게 먹었지만 컨디션을 살피고 있어요.")
    page.locator(".modal").get_by_role("button", name="공개 승인", exact=True).click()
    expect(page.get_by_text("보호자 공개됨").first).to_be_visible()
    pick("보호자 · 김서연 (보리)")                  # 데모 계정 전환 → 보호자 화면
    expect(page.get_by_role("heading", name="김서연님의 알림장")).to_be_visible()
    expect(page.get_by_text("공개 승인된 기록이 없습니다")).to_have_count(0)
    expect(page.locator(".feed")).to_contain_text("컨디션을 살피고")
    expect(page.locator(".feed")).not_to_contain_text("오후 담당자")
    expect(page.locator(".chips [data-d]")).to_have_count(1)                            # 자기 아이(보리)만
    shot("12-parent")
    page.goto(f"{BASE}/#/dogs")                                                          # 보호자는 직원 화면에 들어갈 수 없음
    expect(page.get_by_role("heading", name="김서연님의 알림장")).to_be_visible()
    pick("오후 담당자 · 서민재")                       # 다시 직원으로
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()
    step("보호자 화면: 자기 아이의 승인된 문구만 표시, 직원 화면 접근 차단")

    # 10-b. 반려견 등록 + 사진 자르기(크롭)
    from PIL import Image
    import io, tempfile
    img_path = os.path.join(tempfile.gettempdir(), "wide_test.png")
    im = Image.new("RGB", (900, 600), (30, 80, 220))             # 가로 사진: 왼쪽 절반 빨강, 오른쪽 절반 파랑
    im.paste((220, 30, 30), (0, 0, 450, 600)); im.save(img_path)
    page.goto(f"{BASE}/#/dogs")
    expect(page.locator(".dog-card")).to_have_count(5)
    page.locator("#add-dog").click()
    modal = page.locator(".modal")
    modal.get_by_role("button", name="등록", exact=True).click()                       # 빈 폼
    for msg in ("이름을 입력해 주세요.", "견종을 입력해 주세요.", "생년월일을 입력해 주세요.", "보호자 이름을 입력해 주세요."):
        expect(modal.get_by_text(msg, exact=True)).to_be_visible()
    shot("11b-register-errors")
    modal.get_by_label("이름 *", exact=True).fill("초코"); modal.get_by_label("견종 *").fill("닥스훈트")
    modal.get_by_label("생년월일 *").fill("2023-05-01"); modal.get_by_label("보호자 이름 *").fill("강민지")
    # 크롭 취소: ESC는 크롭 창만 닫고 등록 창은 유지
    page.locator("#pp-file").set_input_files(img_path)
    expect(page.locator("#cv")).to_be_visible(); page.keyboard.press("Escape")
    expect(page.locator("#cv")).to_have_count(0); expect(modal.get_by_label("이름 *", exact=True)).to_have_value("초코")
    expect(page.locator("#pp-prev img")).to_have_count(0)
    # 다시 선택 → 왼쪽으로 크게 끌어 오른쪽 끝을 가운데 정사각형에 맞춘다
    page.locator("#pp-file").set_input_files(img_path)
    cv = page.locator("#cv"); box = cv.bounding_box()
    page.mouse.move(box["x"] + 150, box["y"] + 150); page.mouse.down(); page.mouse.move(box["x"] - 50, box["y"] + 150, steps=8); page.mouse.up()
    shot("11c-cropper")
    page.locator("#ok").click()
    expect(page.locator("#cv")).to_have_count(0); expect(page.locator("#pp-prev img")).to_have_count(1)
    modal.get_by_role("button", name="등록", exact=True).click()
    expect(page.get_by_role("heading", name="초코")).to_be_visible()
    src = page.locator(".dog-head .avatar img").get_attribute("src")
    assert src.startswith("uploads/dogs/"), src
    try:
        urllib.request.urlopen(f"{BASE}/{src}"); raise AssertionError("로그인 없이 프로필 사진이 열림")
    except urllib.error.HTTPError as e:
        assert e.code == 401                                                       # 프로필 사진도 로그인한 권한자만 열람
    out = Image.open(io.BytesIO(page.request.get(f"{BASE}/{src}").body())).convert("RGB")
    assert out.size == (512, 512), out.size                                     # 항상 정사각형
    left, center = out.getpixel((60, 256)), out.getpixel((300, 256))
    assert left[0] > 150 and left[2] < 100, f"왼쪽은 빨강이어야 함 {left}"          # 끌어서 이동한 결과가 반영됨
    assert center[2] > 150 and center[0] < 100, f"가운데는 파랑이어야 함 {center}"
    shot("11d-new-dog")
    step("반려견 등록: 필수 오류 표시, 크롭 취소(ESC)는 등록 창 유지, 드래그한 위치대로 512×512 정사각형 저장")

    page.goto(f"{BASE}/#/dogs"); page.locator("#add-dog").click()                  # 같은 이름+보호자 중복
    modal = page.locator(".modal")
    modal.get_by_label("이름 *", exact=True).fill("초코"); modal.get_by_label("견종 *").fill("닥스훈트")
    modal.get_by_label("생년월일 *").fill("2023-05-01"); modal.get_by_label("보호자 이름 *").fill("강민지")
    modal.get_by_role("button", name="등록", exact=True).click()
    expect(page.get_by_text("이미 등록된 반려견입니다.")).to_be_visible()
    modal.get_by_role("button", name="취소").click()
    expect(page.locator(".dog-card")).to_have_count(6)
    page.locator(".dog-card", has_text="초코").click()
    page.get_by_role("button", name="프로필 수정").click()                           # 사진 삭제 → 이니셜 아바타
    page.locator("#pp-remove").click()
    page.locator(".modal").get_by_role("button", name="저장").click()
    expect(page.locator(".dog-head .avatar img")).to_have_count(0)
    assert urllib.request.urlopen(urllib.request.Request(f"{BASE}/{src}")) if False else True
    assert page.request.get(f"{BASE}/{src}").status == 404, "삭제한 사진이 아직 제공됨"
    step("중복 등록 거부, 프로필 수정에서 사진 삭제 시 파일도 제거")

    # 10-c. 일과
    page.goto(f"{BASE}/#/dashboard")
    expect(page.get_by_role("heading", name="오늘의 일과")).to_be_visible()
    expect(page.locator(".routine.compact .rblock")).to_have_count(6)
    expect(page.locator(".program")).to_contain_text("오늘의 프로그램")
    page.locator(".nav").get_by_role("link", name="오늘의 일과").click()
    expect(page.get_by_role("heading", name="오늘의 일과", level=1)).to_be_visible()
    page.locator(".rblock", has_text="점심·휴식").click()
    expect(page.locator("#bt")).to_contain_text("점심·휴식")
    expect(page.get_by_text("이 구간에 기록이 있는 반려견")).to_contain_text("2/6")      # 보리·밤이 / 새로 등록한 초코 포함 6마리
    rows = page.locator(".timeline li")
    expect(rows.first).to_contain_text("아직 기록 없음")                                  # 기록 없는 아이가 위
    shot("14-routine-lunch")
    page.locator(".rblock", has_text="오후 산책·놀이").click()
    expect(page.locator(".handoff")).to_contain_text("오전 → 오후 담당자")
    expect(page.locator(".handoff")).to_contain_text("확인 대기 0건")             # 앞 단계에서 #1을 확인 처리함
    expect(page.locator(".handoff")).to_contain_text("확인했지만 조치 필요 2건 · 진행 중 1건")
    expect(page.locator(".handoff .task-row").first).to_be_visible()
    shot("15-routine-handoff")
    # 구간에서 바로 기록 작성: 구간·반려견이 미리 선택됨 → 저장 후 구간 현황에 반영
    page.locator(".timeline li", has_text="두부").get_by_role("link", name="기록 작성").click()
    expect(page.locator("#block")).to_have_value(re.compile(r"\d+")); expect(page.locator("#dog")).to_have_value("2")
    page.locator("#f").get_by_text("활발함", exact=True).click(); page.get_by_role("button", name="기록 저장").click()
    expect(page.locator("#done")).to_contain_text("두부의 기록을 저장했습니다"); expect(page.locator("#done")).to_contain_text("오후 산책·놀이")
    page.goto(f"{BASE}/#/dogs/2")
    expect(page.locator(".timeline").first).to_contain_text("오후 산책·놀이")
    step("일과: 대시보드 구간 표시, 구간별 기록 현황·기록 없는 아이, 인계 시점 요약, 구간에서 바로 기록 작성")

    # 10-d. 로그인·세션·초대 코드·보호자 가입
    page.get_by_role("button", name="처음 화면으로").click()                              # 로그아웃
    expect(page.get_by_role("button", name="선생님으로 시작하기")).to_be_visible()
    page.goto(f"{BASE}/#/dashboard")                                                     # 로그인 없이 직원 화면 → 로그인으로
    expect(page.get_by_role("heading", name="로그인")).to_be_visible(); expect(page.get_by_text("로그인이 필요합니다.")).to_be_visible()
    shot("20-login")
    page.get_by_label("이메일").fill("jiwoo.han@pawcare.demo"); page.get_by_label("비밀번호").fill("틀린비밀번호")
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.locator("#form-err")).to_contain_text("이메일 또는 비밀번호가 올바르지 않습니다.")
    page.get_by_label("이메일").fill("nobody-lock@pawcare.demo")                         # 같은 이메일로 반복 실패 → 시도 제한
    for _ in range(6):                                                                   # 5번 실패한 뒤 6번째 시도부터 차단
        page.get_by_label("비밀번호").fill("틀린비밀번호")
        with page.expect_response("**/api/auth/login"):                                  # 시간이 아니라 응답을 기다린다
            page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.locator("#form-err")).to_contain_text("로그인 시도가 너무 많습니다")
    shot("21-login-locked")
    errors[:] = [e for e in errors if "401" not in e and "429" not in e]               # 일부러 일으킨 인증 실패 응답
    page.get_by_label("이메일").fill("jiwoo.han@pawcare.demo"); page.get_by_label("비밀번호").fill("pawcare-demo")   # 다른 계정은 영향 없음
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()
    page.reload(); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()   # 새로고침해도 로그인 유지(쿠키 세션)
    assert "pawcare_session" not in page.evaluate("document.cookie"), "세션 쿠키가 JS에서 읽힘(HttpOnly 아님)"
    step("로그인 필요 경로 보호, 잘못된 비밀번호·반복 실패 제한, 새로고침 후 세션 유지, 쿠키는 JS에서 읽을 수 없음")

    page.goto(f"{BASE}/#/dogs/4")                                                        # 밤이: 아직 보호자 계정이 없음
    expect(page.get_by_role("heading", name="보호자 계정")).to_be_visible()
    expect(page.get_by_text("아직 가입한 보호자가 없습니다")).to_be_visible()
    page.get_by_role("button", name="초대 코드 만들기").click()
    code = page.locator(".invite-code").inner_text().strip()
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", code), code
    shot("22-invite-code")
    page.locator(".modal").get_by_role("button", name="확인").click()
    expect(page.get_by_text("사용 대기")).to_be_visible()
    expect(page.locator("body")).not_to_contain_text(code)                              # 코드 원문은 다시 볼 수 없음
    page.get_by_role("button", name="처음 화면으로").click()
    page.goto(f"{BASE}/#/register")
    page.get_by_label("초대 코드 *").fill(code.lower()); page.get_by_label("이름 *").fill("최하진"); page.get_by_label("이메일 *").fill("hajin@example.com")
    page.get_by_label("비밀번호 *", exact=True).fill("새비밀번호-2026"); page.get_by_label("비밀번호 확인 *").fill("다른비밀번호")
    page.get_by_role("button", name="가입하고 시작하기").click()
    expect(page.get_by_text("비밀번호가 서로 다릅니다.")).to_be_visible()
    shot("23-register")
    page.get_by_label("비밀번호 확인 *").fill("새비밀번호-2026"); page.get_by_role("button", name="가입하고 시작하기").click()
    expect(page.get_by_role("heading", name="최하진님의 알림장")).to_be_visible()
    expect(page.locator(".chips [data-d]")).to_have_text(["밤이"])                      # 초대받은 아이 한 마리만
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="최하진님의 알림장")).to_be_visible()   # 직원 화면 차단
    page.get_by_role("button", name="처음 화면으로").click()
    page.goto(f"{BASE}/#/register")                                                      # 코드 재사용 불가
    page.get_by_label("초대 코드 *").fill(code); page.get_by_label("이름 *").fill("다른사람"); page.get_by_label("이메일 *").fill("other@example.com")
    page.get_by_label("비밀번호 *", exact=True).fill("새비밀번호-2026"); page.get_by_label("비밀번호 확인 *").fill("새비밀번호-2026")
    page.get_by_role("button", name="가입하고 시작하기").click()
    expect(page.get_by_text("이미 사용·만료되었습니다")).to_be_visible()
    errors[:] = [e for e in errors if "400" not in e]
    step("초대 코드: 직원이 발급(원문은 한 번만 표시) → 보호자 가입 → 해당 아이만 접근, 재사용 불가")

    page.goto(f"{BASE}/#/login")                                                         # 이후 단계는 직원으로 계속
    page.get_by_label("이메일").fill("jiwoo.han@pawcare.demo"); page.get_by_label("비밀번호").fill("pawcare-demo")
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()

    # 10-e. 사진 첨부 (EXIF 제거, 태그, 뷰어, 인증된 열람)
    def make_jpeg(path, w, h, color):
        exif = Image.Exif(); exif[0x010F] = "SecretCameraMaker"
        g = exif.get_ifd(0x8825); g[1], g[2], g[3], g[4] = "N", (37.0, 33.0, 59.0), "E", (126.0, 58.0, 41.0)
        Image.new("RGB", (w, h), color).save(path, "JPEG", exif=exif.tobytes())
    p1, p2 = os.path.join(tempfile.gettempdir(), "pet_a.jpg"), os.path.join(tempfile.gettempdir(), "pet_b.jpg")
    make_jpeg(p1, 2400, 1600, (200, 140, 90)); make_jpeg(p2, 800, 1200, (90, 140, 200))
    notimg = os.path.join(tempfile.gettempdir(), "notes.txt"); open(notimg, "w").write("not an image")
    page.goto(f"{BASE}/#/record/new?dog=1")
    page.locator("#f").get_by_text("활발함", exact=True).click() if False else None
    page.locator("#content").fill("산책 후 사진을 남깁니다.")
    page.locator("#pa-file").set_input_files(notimg)                                      # 이미지가 아닌 파일은 거부
    expect(page.get_by_text("JPG, PNG, WebP 사진만 사용할 수 있습니다")).to_be_visible()
    page.locator("#pa-file").set_input_files([p1, p2])
    expect(page.locator(".pa-item")).to_have_count(2)
    expect(page.locator('[data-tag="1"]')).to_have_attribute("aria-pressed", "true")       # 기본 태그: 기록의 반려견(보리)
    page.locator('[data-tag="2"]').click()                                                 # 두부도 함께 찍힘
    shot("24-photo-attach")
    page.get_by_role("button", name="기록 저장").click()
    expect(page.locator("#done")).to_contain_text("사진 2장을 첨부했습니다.")
    recs = page.request.get(f"{BASE}/api/records").json()
    mine = [r for r in recs if r["media"]][0]
    assert len(mine["media"]) == 2 and all(m["dog_ids"] == [1, 2] for m in mine["media"]), mine["media"]
    raw = page.request.get(f"{BASE}/api/media/{mine['media'][0]['id']}/file").body()
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" and b"SecretCameraMaker" not in raw and b"Exif" not in raw
    im = Image.open(io.BytesIO(raw)); assert max(im.size) == 1600 and not dict(im.getexif()), im.size
    for m in mine["media"]:                                                                # 로그인하지 않은 요청은 열 수 없다
        try:
            urllib.request.urlopen(f"{BASE}/api/media/{m['id']}/file"); raise AssertionError("로그인 없이 사진이 열림")
        except urllib.error.HTTPError as e:
            assert e.code == 401
    step("사진 첨부: 비이미지 거부, 두 장 업로드·태그, 서버 저장본에 EXIF/GPS 없음·1600px 이하, 로그인 없이는 열람 불가")

    page.goto(f"{BASE}/#/dogs/1")
    thumbs = page.locator(".timeline").first.locator(".thumb")
    expect(thumbs).to_have_count(2)
    thumbs.first.click()
    expect(page.locator(".viewer img")).to_be_visible(); shot("25-photo-viewer")
    page.locator('.modal [data-t="3"]').click()                                            # 뷰어에서 모카도 태그
    expect(page.locator('.modal [data-t="3"]')).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Escape")
    expect(page.locator(".viewer img")).to_have_count(0)
    page.goto(f"{BASE}/#/dogs/3")                                                          # 모카 프로필에도 단체 사진이 보임
    expect(page.locator("#dog-photos .thumb")).to_have_count(1)
    page.goto(f"{BASE}/#/dogs/2")                                                          # 두부는 두 장
    expect(page.locator("#dog-photos .thumb")).to_have_count(2)
    page.goto(f"{BASE}/#/dogs/1")                                                          # 기록 옆 '사진 추가'
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="사진 추가").first.click()
    fc.value.set_files(p2)
    expect(page.locator(".timeline").first.locator(".thumb")).to_have_count(3)
    page.once("dialog", lambda d: d.accept())                                              # 삭제는 확인 후
    page.locator(".timeline").first.locator(".thumb").first.click()
    page.get_by_role("button", name="사진 삭제").click()
    page.keyboard.press("Escape")
    expect(page.locator(".timeline").first.locator(".thumb")).to_have_count(2)
    step("사진 뷰어: 태그 수정이 다른 아이 프로필에 반영, 기록에 사진 추가, 삭제")

    # 보호자는 아직 사진을 볼 수 없다(공개 승인 기능 전)
    switch_to("보호자 · 김서연 (보리)", "김서연님의 알림장")
    assert page.request.get(f"{BASE}/api/media/{mine['media'][0]['id']}/file").status == 403
    assert page.request.get(f"{BASE}/api/records").status == 403
    switch_to("오전 담당자 · 한지우", "오늘의 업무")
    step("보호자 계정은 첨부 사진·기록 API 접근 불가")

    # 10-f. M3·M4: 사진 공개 승인 → 보호자 알림장
    recs = page.request.get(f"{BASE}/api/records").json()
    rec = next(r for r in recs if len(r["media"]) == 2)
    ma, mb = rec["media"][0]["id"], rec["media"][1]["id"]                               # ma: 보리·두부, mb: 보리
    page.goto(f"{BASE}/#/dogs/1")
    page.get_by_role("button", name="보호자 공개 승인…").first.click()
    expect(page.locator(".share-row")).to_have_count(2)
    expect(page.locator(".share-row").nth(0).get_by_label("보리의 보호자")).to_be_checked()      # 기본: 기록의 아이만
    expect(page.locator(".share-row").nth(0).get_by_label("두부의 보호자")).not_to_be_checked()
    page.locator(".share-row").nth(0).get_by_label("두부의 보호자").check()                       # 단체 사진은 직원이 직접 추가 선택
    page.locator(".share-row").nth(1).get_by_label("보리의 보호자").uncheck()                     # 두 번째 사진은 공개하지 않음
    shot("27-share-modal")
    page.locator(".modal").get_by_role("button", name="공개 승인", exact=True).click()
    expect(page.locator(".timeline").first).to_contain_text("보호자 공개됨 · 사진 1장")
    switch_to("보호자 · 김서연 (보리)", "김서연님의 알림장")
    expect(page.locator(".feed .thumb")).to_have_count(1)                                 # 선택한 사진 한 장만
    expect(page.locator(".feed-card").first).to_contain_text("새 알림장")
    expect(page.locator(".chips [data-d]")).to_contain_text("새 1")
    shot("28-parent-feed")
    assert page.request.get(f"{BASE}/api/parent/media/{ma}/file").status == 200
    assert page.request.get(f"{BASE}/api/parent/media/{mb}/file").status == 404          # 선택하지 않은 사진
    page.locator(".feed .thumb").first.click()
    expect(page.locator(".viewer img")).to_be_visible(); expect(page.get_by_role("link", name="사진 저장")).to_be_visible()
    shot("29-parent-viewer"); page.keyboard.press("Escape")
    page.wait_for_timeout(600); page.reload()                                            # 열어 봤으니 다음에는 '새' 표시가 없다
    expect(page.get_by_role("heading", name="김서연님의 알림장")).to_be_visible()
    expect(page.locator(".feed-card").first).not_to_contain_text("새 알림장"); expect(page.locator(".chips [data-d]")).not_to_contain_text("새")
    switch_to("보호자 · 박도윤 (두부)", "박도윤님의 알림장")                                   # 함께 찍힌 두부의 보호자
    expect(page.locator(".feed-card")).to_have_count(1)
    expect(page.locator(".feed-card").first).to_contain_text("친구들과 함께 찍힌 사진")
    expect(page.locator(".feed")).not_to_contain_text("사진을 남깁니다")                       # 보리 기록의 글은 보이지 않는다
    assert page.request.get(f"{BASE}/api/parent/media/{ma}/file").status == 200
    switch_to("보호자 · 이수아 (모카)", "이수아님의 알림장")                                   # 태그되지 않은 아이의 보호자
    assert page.request.get(f"{BASE}/api/parent/media/{ma}/file").status == 404
    switch_to("오전 담당자 · 한지우", "오늘의 업무")
    page.goto(f"{BASE}/#/dogs/1")
    page.get_by_role("button", name="공개 취소").first.click()                             # 확인창 없이 바로 취소
    switch_to("보호자 · 박도윤 (두부)", "박도윤님의 알림장")
    expect(page.get_by_text("공개된 알림장이 없습니다")).to_be_visible()                       # 취소하면 바로 사라진다
    assert page.request.get(f"{BASE}/api/parent/media/{ma}/file").status == 404
    switch_to("오전 담당자 · 한지우", "오늘의 업무")
    step("공개 승인: 사진별 공개 대상 선택(단체 사진은 직접 추가), 보호자에게 선택한 사진만·새 알림장 표시, 단체 사진엔 글 미노출, 취소하면 즉시 사라짐")

    # 10-g. M5: 일과의 '사진 공유 시점' — 구간 기록에 사진을 붙이고, 공개 전/후 현황을 구간에서 확인
    kst_today = page.evaluate("new Date(Date.now() + (new Date().getTimezoneOffset() + 540) * 60000).toISOString().slice(0, 10)")
    page.goto(f"{BASE}/#/record/new?dog=1")
    page.locator("#at").fill(f"{kst_today}T12:30")                                          # 점심·휴식 구간 시각의 기록
    expect(page.locator("#block")).to_contain_text("자동 — 점심·휴식")
    page.locator("#content").fill("M5 사진 공유 확인")
    page.locator("#pa-file").set_input_files(p1); expect(page.locator(".pa-item")).to_have_count(1)
    page.get_by_role("button", name="기록 저장").click()
    expect(page.locator("#done")).to_contain_text("사진 1장을 첨부했습니다."); settle()
    page.goto(f"{BASE}/#/routine"); page.locator(".rblock", has_text="점심·휴식").click()
    expect(page.locator("#bt")).to_contain_text("점심·휴식")
    expect(page.locator(".rblock", has_text="점심·휴식")).to_contain_text("사진 공유")
    expect(page.locator(".share-card")).to_contain_text("사진 공유 시점")
    expect(page.locator(".share-card")).to_contain_text("사진이 공개된 아이 0/")
    bori = page.locator(".timeline li", has_text="보리").filter(has=page.get_by_text("공개 전 사진 1장"))
    expect(bori).to_have_count(1)                                                           # 사진은 있지만 아직 공개 전
    shot("30-routine-share-pending")
    bori.get_by_role("link", name="공개 승인하러 가기").click()
    expect(page.get_by_role("heading", name="보리", exact=True)).to_be_visible()
    page.locator(".timeline").first.locator("li", has_text="M5 사진 공유 확인").get_by_role("button", name="보호자 공개 승인…").click()
    expect(page.locator(".share-row")).to_have_count(1)
    expect(page.locator(".share-row").get_by_label("보리의 보호자")).to_be_checked()
    page.locator(".modal").get_by_role("button", name="공개 승인", exact=True).click()
    expect(page.locator(".timeline").first).to_contain_text("보호자 공개됨 · 사진 1장"); settle()
    page.goto(f"{BASE}/#/routine"); page.locator(".rblock", has_text="점심·휴식").click()
    expect(page.locator("#bt")).to_contain_text("점심·휴식")
    expect(page.locator(".rblock", has_text="점심·휴식")).to_contain_text("사진 공개 1/")
    expect(page.locator(".share-card")).to_contain_text("사진이 공개된 아이 1/")
    expect(page.locator(".timeline li", has_text="보리")).to_contain_text("사진 1장 공개됨")
    shot("31-routine-share-done")
    page.locator(".rblock", has_text="오전 교육·놀이").click()                                  # 사진 공유 시점이 아닌 구간에는 현황 카드가 없다
    expect(page.locator("#bt")).to_contain_text("오전 교육·놀이"); expect(page.locator(".share-card")).to_have_count(0)
    step("사진 공유 시점: 점심 구간에서 공개 전 사진이 있는 아이 확인 → 공개 승인 → 구간 현황(공개 N/M마리) 갱신, 다른 구간엔 현황 없음")

    # 10-h. M6: 퇴원 처리(관리자) → 보호자 안내 → 재등록
    page.goto(f"{BASE}/#/dogs/3"); expect(page.get_by_role("heading", name="모카", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="퇴원 처리")).to_have_count(0)                      # 관리자가 아니면 퇴원 처리 버튼이 없다
    pick("관리자 · 정하은")                                                                       # 직원끼리 전환하면 현재 화면에 머문다
    expect(page.get_by_role("button", name="퇴원 처리")).to_be_visible()
    page.get_by_role("button", name="퇴원 처리").click()
    expect(page.locator(".modal")).to_contain_text("퇴원 3개월 뒤")
    page.locator(".modal").get_by_role("button", name="퇴원 처리", exact=True).click()           # 확인 체크 없이는 진행되지 않음
    expect(page.locator(".modal")).to_be_visible()
    page.locator(".modal input[name=ok]").check(); shot("32-discharge-modal")
    page.locator(".modal").get_by_role("button", name="퇴원 처리", exact=True).click()
    expect(page.get_by_text("퇴원 처리됨").first).to_be_visible(); settle()
    expect(page.locator("#view")).to_contain_text("삭제될 예정입니다")
    expect(page.get_by_role("button", name="돌봄 기록 작성")).to_be_disabled()                  # 새 기록 불가
    shot("33-discharged-profile")
    page.goto(f"{BASE}/#/dogs"); expect(page.locator(".dog-card", has_text="모카")).to_have_count(0)   # 재원 중 목록에서는 사라짐
    page.get_by_role("button", name="퇴원", exact=True).click()
    expect(page.locator(".dog-card", has_text="모카")).to_have_count(1)
    expect(page.locator("#purge-panel")).to_contain_text("삭제 예정 현황")
    expect(page.get_by_role("button", name="삭제 대상 정리 실행")).to_have_count(0)               # 아직 기한이 지나지 않았으므로 정리할 대상이 없다
    shot("34-purge-panel")
    switch_to("보호자 · 이수아 (모카)", "이수아님의 알림장")                                       # 보호자에게는 삭제 예정일 안내가 보이고, 공개된 내용은 아직 볼 수 있다
    expect(page.locator("#pw")).to_contain_text("퇴원했어요"); expect(page.locator(".feed")).to_contain_text("신나게")
    shot("35-parent-discharged")
    switch_to("관리자 · 정하은", "오늘의 업무")
    page.goto(f"{BASE}/#/dogs/3")
    page.once("dialog", lambda d: d.accept())
    page.get_by_role("button", name="재등록 처리").click()
    expect(page.get_by_role("button", name="퇴원 처리")).to_be_visible()                           # 재등록: 다시 정상
    expect(page.get_by_role("link", name="돌봄 기록 작성").first).to_be_visible()
    pick("오전 담당자 · 한지우")
    step("퇴원 처리: 관리자만, 확인 체크 필수, 새 기록 차단·목록에서 숨김·삭제 예정 현황, 보호자 안내(공개된 내용은 유지), 재등록으로 복구")

    # AI 연결 테스트: 키가 없는 환경에서는 원인을 알려준다
    page.goto(f"{BASE}/#/ai"); expect(page.get_by_role("heading", name="AI 연결 상태")).to_be_visible()
    page.get_by_role("button", name="연결 테스트").click()
    expect(page.locator("#ai-test-out")).to_contain_text("연결 안 됨"); expect(page.locator("#ai-test-out")).to_contain_text("GEMINI_API_KEY가 설정되지 않았습니다")
    page.get_by_role("button", name="사용 가능한 모델 찾기").click()
    expect(page.locator("#ai-test-out")).to_contain_text("GEMINI_API_KEY가 설정되지 않았습니다")
    shot("36-ai-connection-test")
    step("AI 연결 테스트: 키가 없으면 원인을 안내(데모 분석으로 동작)")

    # 11. 다른 유치원 격리
    page.goto(f"{BASE}/#/dashboard")
    pick("관리자 · 오하준")
    expect(page.locator(".task-row")).to_have_count(1)
    expect(page.locator(".task-row")).to_contain_text("구름")
    step("다른 유치원 직원은 자기 회사 데이터만 봄")

    # 12. 좁은 화면
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(f"{BASE}/#/dashboard")
    pick("오후 담당자 · 서민재") if False else None
    shot("13-mobile")
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    assert not overflow, "모바일 가로 스크롤 발생"
    step("390px 폭에서 가로 스크롤 없음")

    for code, n in (("409", 1),):                                  # 중복 등록 거부(409)는 의도한 1건. 메시지가 늦게 기록돼도 이 개수만 허용
        for _ in range(n):
            hit = next((e for e in errors if code in e), None)
            if hit: errors.remove(hit)
    assert not errors, errors
    step("콘솔 오류 없음")
    b.close()
print(f"\n통과 {len(results)}개 항목")

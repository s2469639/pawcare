"""핵심 시연 시나리오 E2E (실제 브라우저 조작). 사용법:
   서버 실행 후  python tests/e2e_scenario.py [BASE_URL]
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
    tasks_before = int(urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/dashboard", headers={"X-Staff-Id": "1"})).read().count(b'"title"'))
    assert tasks_before == 4, tasks_before

    # 4. AI 제안
    page.get_by_role("link", name="후속 업무 제안 받기").click()
    expect(page.locator(".mode")).to_contain_text("데모 분석")
    expect(page.locator(".sugg h3")).to_have_text("오후 배변 상태 확인")
    expect(page.locator(".sugg")).to_contain_text("서민재")
    shot("06-ai")
    page.get_by_role("button", name="제안 무시").click()
    expect(page.get_by_text("업무가 생성되지 않았습니다")).to_be_visible()
    d = urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/dashboard", headers={"X-Staff-Id": "1"})).read()
    assert d.count(b'"title"') == 4, "무시했는데 업무가 생성됨"
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
    page.locator("#who").select_option(label="오후 담당자 · 서민재")
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
    expect(page.locator(".timeline")).to_contain_text("묽은 변")
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
    expect(page.locator(".timeline")).to_contain_text("묽은 변")
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
    expect(page.get_by_text("보호자 공개 승인됨")).to_be_visible()
    page.goto(f"{BASE}/#/parent")
    expect(page.get_by_text("공개 승인된 기록이 없습니다")).to_have_count(0)
    expect(page.locator(".phone")).to_contain_text("컨디션을 살피고")
    expect(page.locator(".phone")).not_to_contain_text("오후 담당자")
    shot("12-parent")
    step("보호자 미리보기는 승인된 문구만 표시")

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
    out = Image.open(io.BytesIO(urllib.request.urlopen(f"{BASE}/{src}").read())).convert("RGB")
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
    try:
        urllib.request.urlopen(f"{BASE}/{src}"); raise AssertionError("삭제한 사진이 아직 제공됨")
    except urllib.error.HTTPError as e:
        assert e.code == 404
    errors[:] = [e for e in errors if "409" not in e and "404" not in e]   # 중복 등록(409)·삭제한 사진 조회(404)는 일부러 일으킨 응답
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
    expect(page.locator(".timeline")).to_contain_text("오후 산책·놀이")
    step("일과: 대시보드 구간 표시, 구간별 기록 현황·기록 없는 아이, 인계 시점 요약, 구간에서 바로 기록 작성")

    # 11. 다른 유치원 격리
    page.goto(f"{BASE}/#/dashboard")
    page.locator("#who").select_option(label="관리자 · 오하준")
    expect(page.locator(".task-row")).to_have_count(1)
    expect(page.locator(".task-row")).to_contain_text("구름")
    step("다른 유치원 직원은 자기 회사 데이터만 봄")

    # 12. 좁은 화면
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(f"{BASE}/#/dashboard")
    page.locator("#who").select_option(label="오후 담당자 · 서민재") if False else None
    shot("13-mobile")
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    assert not overflow, "모바일 가로 스크롤 발생"
    step("390px 폭에서 가로 스크롤 없음")

    assert not errors, errors
    step("콘솔 오류 없음")
    b.close()
print(f"\n통과 {len(results)}개 항목")

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

    page.goto(f"{BASE}/#/dogs/3")
    page.set_viewport_size({"width": 1280, "height": 820})
    page.goto(f"{BASE}/#/parent"); page.get_by_role("button", name="모카").click()
    expect(page.locator(".phone")).to_contain_text("신나게"); shot("12-parent-preview")

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

    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible(); shot("13-mobile-dashboard")
    b.close()

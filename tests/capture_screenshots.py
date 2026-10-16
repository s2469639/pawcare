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

    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible(); shot("13-mobile-dashboard")
    b.close()

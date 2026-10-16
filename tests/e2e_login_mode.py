"""실제 로그인 모드(DEMO_MODE 끔) 검증. 사용법: DEMO_MODE 없이 서버 실행 후  python tests/e2e_login_mode.py [BASE_URL]
이 모드에서는 데모 전환·초기화·데모 계정 목록이 없어야 하고, 로그인해야만 화면을 쓸 수 있다.
(샘플 DB의 데모 계정으로 로그인하므로 샘플 데이터가 들어 있는 DB가 필요하다.)"""
import glob
import sys
import urllib.error
import urllib.request

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def status(method, path):
    try:
        return urllib.request.urlopen(urllib.request.Request(BASE + path, method=method, data=b"{}" if method == "POST" else None,
                                                             headers={"Content-Type": "application/json"})).status
    except urllib.error.HTTPError as e:
        return e.code


assert status("GET", "/api/health") == 200
assert status("GET", "/api/auth/demo-accounts") == 404 and status("POST", "/api/demo/reset") == 404 and status("POST", "/api/auth/demo-login") in (404, 422)
print("✔ 데모 전용 API(계정 목록·초기화·데모 로그인)는 로그인 모드에서 비활성")
assert status("GET", "/api/dashboard") == 401 and status("GET", "/api/dogs") == 401 and status("GET", "/api/parent/dogs") == 401
print("✔ 로그인 없이는 업무·반려견·보호자 API 모두 401")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0], args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1280, "height": 820})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts.g" not in m.text and "ERR_" not in m.text and "401" not in m.text else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    expect(page.get_by_text("직원 로그인")).to_be_visible()
    page.get_by_role("button", name="선생님으로 시작하기").click()
    expect(page.get_by_role("heading", name="직원 로그인")).to_be_visible()
    expect(page.get_by_text("데모 계정으로 입장")).to_have_count(0)                      # 데모 입장 버튼 없음
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="로그인")).to_be_visible()
    page.get_by_label("이메일").fill("minjae.seo@pawcare.demo"); page.get_by_label("비밀번호").fill("pawcare-demo")
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()
    expect(page.locator("#who")).to_have_count(0)                                       # 계정 전환 드롭다운 없음
    expect(page.locator(".who-name")).to_contain_text("서민재")
    expect(page.locator("#reset")).to_have_count(0)                                     # 데이터 초기화 버튼 없음
    page.reload(); expect(page.get_by_role("heading", name="오늘의 업무")).to_be_visible()
    page.get_by_role("button", name="로그아웃").click()
    expect(page.get_by_role("button", name="선생님으로 시작하기")).to_be_visible()
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="로그인")).to_be_visible()   # 로그아웃 후 접근 불가
    page.go_back(); page.go_back()
    expect(page.get_by_role("heading", name="오늘의 업무")).to_have_count(0)
    page.goto(f"{BASE}/#/login?as=parent")
    page.get_by_label("이메일").fill("seoyeon.kim@pawcare.demo"); page.get_by_label("비밀번호").fill("pawcare-demo")
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_role("heading", name="김서연님의 알림장")).to_be_visible()
    expect(page.locator("#who")).to_have_count(0)
    page.goto(f"{BASE}/#/dashboard"); expect(page.get_by_role("heading", name="김서연님의 알림장")).to_be_visible()   # 보호자는 직원 화면 불가
    print("✔ 로그인 모드: 직원/보호자 로그인·로그아웃, 데모 UI 없음, 역할별 접근 제한, 새로고침 후 유지")
    assert not errors, errors
    print("✔ 콘솔 오류 없음")
    b.close()

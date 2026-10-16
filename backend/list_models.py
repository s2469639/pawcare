"""내 Gemini API 키로 사용할 수 있는 모델 목록을 출력한다.

사용법:  python -m backend.list_models
.env의 GEMINI_API_KEY를 읽어 Google에만 요청하며, 키는 화면에 출력하지 않는다.
"""
import os
import sys

import httpx

from .main import load_env

URL = "https://generativelanguage.googleapis.com/v1beta/models"


def fetch(key: str) -> list[dict]:
    models, token = [], None
    while True:
        params = {"pageSize": 100, **({"pageToken": token} if token else {})}
        r = httpx.get(URL, params=params, headers={"x-goog-api-key": key}, timeout=20)
        r.raise_for_status()
        data = r.json()
        models += data.get("models", [])
        token = data.get("nextPageToken")
        if not token:
            return models


def main() -> int:
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY가 없습니다. 프로젝트 맨 위 폴더의 .env 파일에 GEMINI_API_KEY=키 를 먼저 넣어 주세요.")
        return 1
    try:
        models = fetch(key)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = {400: "키 형식이 올바르지 않거나 잘못 복사되었을 수 있습니다.", 403: "키가 거부되었습니다. 키가 유효한지, 사용 권한이 있는지 확인해 주세요."}.get(code, "")
        print(f"요청이 실패했습니다 (HTTP {code}). {hint}")
        return 1
    except httpx.HTTPError as e:
        print(f"Google에 연결하지 못했습니다: {type(e).__name__}. 인터넷 연결을 확인해 주세요.")
        return 1
    usable = sorted(m["name"].removeprefix("models/") for m in models if "generateContent" in m.get("supportedGenerationMethods", []))
    if not usable:
        print("generateContent를 지원하는 모델을 찾지 못했습니다.")
        return 1
    print("이 키로 PawCare에 쓸 수 있는 모델 (GEMINI_MODEL에 아래 이름 중 하나를 그대로 넣으세요):\n")
    for n in usable:
        print(("  ★ " if "flash" in n and "lite" not in n else "    ") + n)
    print("\n★ = 빠르고 가벼운 flash 계열(처음 쓰기 좋음). 무료 사용량 한도는 모델마다 다르며, Google AI Studio에서 확인할 수 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

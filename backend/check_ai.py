"""Gemini 연결을 터미널에서 점검한다.   사용법:  python -m backend.check_ai
.env의 GEMINI_API_KEY·GEMINI_MODEL을 읽어 실제로 한 번 호출해 보고, 실패하면 원인을 알려준다(키 값은 출력하지 않는다)."""
import os
import sys

from .main import load_env
from .services import ai_service


def main() -> int:
    load_env()
    key, model = os.environ.get("GEMINI_API_KEY", "").strip(), os.environ.get("GEMINI_MODEL", "").strip()
    print(f"GEMINI_API_KEY : {'설정됨 (길이 %d)' % len(key) if key else '없음'}")
    print(f"GEMINI_MODEL   : {model or '없음'}")
    if key and (key != key.strip('"\'') or " " in key):
        print("  ※ 키에 따옴표나 공백이 섞여 있는 것 같습니다. .env에서 GEMINI_API_KEY=키 형태로(따옴표·공백 없이) 적어 주세요.")
    print("\nGemini에 요청을 보내는 중…")
    r = ai_service.check_connection()
    print(("✔ " if r["ok"] else "✘ ") + r["message"])
    if not r["ok"]:
        print("\n가능한 원인: 키 오타 · 모델 이름 · 무료 사용량 한도 · 인터넷 연결 · .env 위치(프로젝트 맨 위 폴더)")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

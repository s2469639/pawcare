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
    if "--find" in sys.argv:
        if not key:
            print("\nGEMINI_API_KEY가 없어 모델을 찾을 수 없습니다. .env를 확인해 주세요."); return 1
        print("\n내 키로 실제 호출이 되는 모델을 찾는 중… (모델마다 아주 짧은 요청을 보냅니다)")
        try:
            f = ai_service.find_working_models(key)
        except ai_service.AIError as e:
            print("✘ " + e.user_message); return 1
        for t in f["tried"]:
            print(f"  {'✔' if t['result'] == 'ok' else '✘'} {t['model']:<34} {t['note']}")
        if f["working"]:
            print(f"\n✔ 지금 쓸 수 있는 모델: {', '.join(f['working'])}")
            print(f".env에 GEMINI_MODEL={f['working'][0]} 라고 적거나, 모델이 바뀌어도 자동으로 고르게 하려면 GEMINI_MODEL=auto 라고 적으세요.")
            return 0
        print("\n✘ 호출이 되는 모델을 찾지 못했습니다. 키 상태·사용량 한도·인터넷 연결을 확인해 주세요.")
        return 1
    print("\nGemini에 요청을 보내는 중…")
    r = ai_service.check_connection()
    print(("✔ " if r["ok"] else "✘ ") + r["message"])
    if not r["ok"]:
        print("\n가능한 원인: 키 오타 · 모델 종료/이름 · 무료 사용량 한도 · 인터넷 연결 · .env 위치(프로젝트 맨 위 폴더)")
        print("모델 문제라면:  python -m backend.check_ai --find   (실제로 되는 모델을 찾아 줍니다)")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

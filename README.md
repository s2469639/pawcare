# PawCare — AI Care Work Manager

반려견 유치원·호텔 직원의 **돌봄 기록 → 후속 업무 → 담당자 확인 → 조치 완료**를 하나의 흐름으로 연결하는 업무 관리 웹앱 프로토타입입니다. (개인 포트폴리오용)

> 돌봄의 맥락은 이어지고, 확인할 일은 명확해지도록.

모든 반려견·보호자·직원 데이터는 **가상의 샘플**입니다. 실제 알림·메시지 전송, 로그인, 결제 등은 구현하지 않았고 구현된 것처럼 표시하지도 않습니다.

## 실행 방법

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload      # http://localhost:8000
```

- 첫 실행 시 `pawcare.db`(SQLite)가 만들어지고 샘플 데이터가 자동 등록됩니다.
- 화면 좌측 하단 **데모 데이터 초기화**로 언제든 처음 상태로 되돌릴 수 있습니다.
- (선택) AI 연동: `.env.example`을 `.env`로 복사해 `GEMINI_API_KEY`, `GEMINI_MODEL`을 채우면 서버에서 Gemini를 호출합니다. **비워 두면 규칙 기반 '데모 분석'으로 동작하며 UI에 그렇게 표시됩니다.** 키는 서버 환경변수로만 쓰이고 프런트엔드로 전달되지 않습니다.

## 시연 시나리오 (모두 실제 버튼 조작)

1. 역할 선택에서 **선생님으로 시작하기** → 오늘의 업무 대시보드(숫자는 DB에서 계산)
2. 반려견 → **보리** → **돌봄 기록 작성**(배변 · 평소와 다름 + 메모) → 기록 저장
3. **후속 업무 제안 받기** → AI(데모 분석)가 *오후 배변 상태 확인* 제안
4. **제안 무시**(업무 미생성) / **수정하기** / **업무로 등록**(원본 기록과 연결)
5. 상단 *시연 담당자*를 **오후 담당자 · 서민재**로 전환 → 업무 상세에서 **확인 완료**
   (확인 상태만 바뀌고 조치 상태는 *조치 필요* 유지)
6. **조치 시작** → 조치 결과 입력(필수) → **조치 완료** (완료 시각 저장)
7. 대시보드 · 업무 인계 · 반려견 프로필에 같은 상태가 반영됨

## 핵심 설계 원칙

| 원칙 | 구현 |
|---|---|
| 기록 ≠ 업무 처리 | 기록 저장만으로 업무가 생기지 않음. 확인(`pending`/`acknowledged`)과 조치(`todo`/`in_progress`/`completed`)는 **별개 컬럼** |
| AI는 제안, 직원이 확정 | 제안은 DB에 저장되지 않음. 직원이 *업무로 등록*해야 업무가 생성됨 |
| AI 안전장치 | 근거 문장은 원본 기록에 실제 있는 문장만 허용, 진단·투약 표현이 있는 제안은 폐기, 정보가 부족하면 제안하지 않고 사유 표시, 담당자는 기록에 근거가 있을 때만 지정 |
| 담당자 인계 | 확인·조치는 담당자(또는 관리자, 미지정 업무)만 가능. 담당자를 바꿔도 상태는 유지되고 이력이 남음 |
| 보호자 공개 범위 | 직원이 문구를 검토·**공개 승인**한 기록만 미리보기에 표시. 내부 메모·업무 인계·AI 초안은 비공개 |
| 회사(유치원) 단위 구조 | 모든 데이터가 `org_id`로 분리됨. 다른 유치원 직원은 데이터에 접근 불가 |

## 구조

```
backend/   FastAPI + SQLite (database.py, schemas.py, deps.py, seed.py, routes/, services/ai_service.py)
frontend/  Vanilla JS(ES modules) SPA + 직접 작성한 CSS (디자인 토큰: Ivory/Sage/Forest Ink/Clay)
tests/     pytest(API) + e2e_scenario.py(브라우저 시나리오)
```

주요 API: `GET /api/dashboard`, `GET/PATCH /api/dogs…`, `GET/POST /api/records`, `GET/POST/PATCH /api/tasks`, `POST /api/tasks/{id}/actions`(acknowledge · start · complete · comment), `POST /api/ai/suggest-tasks`, `PATCH /api/records/{id}/parent-approval`, `/api/parent/…`.
현재 직원은 `X-Staff-Id` 헤더로 식별합니다(데모용). 오류는 한국어 메시지와 필드별 `errors`로 반환됩니다.

데이터 모델: `organizations`, `staff`, `dogs`, `care_records`(보호자 공개 상태 포함), `tasks`(`source_record_id`로 원본 기록 연결), `task_action_logs`.

## 테스트

```bash
python -m pytest -q                                   # API·규칙 15개
python tests/e2e_scenario.py                          # 서버 실행 후, Playwright 필요: pip install playwright
```

e2e는 샘플 데이터를 초기화한 뒤 위 시나리오 전체(기록 저장, AI 제안 무시/수정/승인, 담당자 전환, 확인·조치 분리, 새로고침 유지, 오류 처리, 보호자 미리보기, 유치원 간 격리, 390px 모바일 가로 스크롤 없음, 콘솔 오류 없음)를 실제 브라우저로 검증합니다.

## 한계 / 아직 하지 않은 것

- 로그인·회원가입 없음: 상단 *시연 담당자* 드롭다운이 로그인을 대신합니다. `org_id` 분리와 `X-Staff-Id` 의존성이 실제 인증으로 교체될 자리입니다.
- Gemini 호출 경로는 이 개발 환경에 키가 없어 **실제 호출은 검증하지 못했습니다.** 응답 검증 로직(`sanitize_model_output`)과 실패 시 데모 분석으로의 대체 동작만 테스트했습니다.
- 푸시/카카오 알림, 예약·결제, 음성, CCTV, 의료 연동, 실시간 다중 사용자 동기화는 범위 밖입니다. 상단의 알림 아이콘은 내게 배정된 확인 대기 업무 수를 보여 줄 뿐 실제 푸시가 아닙니다.
- 보호자 화면은 승인된 기록 미리보기까지입니다(실제 전송 없음).
- 시각 표시는 한국 표준시(KST) 기준입니다.

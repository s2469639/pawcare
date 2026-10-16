# PawCare — AI Care Work Manager

> 돌봄의 맥락은 이어지고, 확인할 일은 명확해지도록.

반려견 유치원·호텔 직원의 **돌봄 기록 → 후속 업무 → 담당자 확인 → 조치 완료**를 하나의 흐름으로 연결하는 업무 관리 웹앱 프로토타입입니다. 개인 포트폴리오용이며, 모든 반려견·보호자·직원 데이터는 **가상의 샘플**입니다.

![오늘의 업무 대시보드](docs/screenshots/02-dashboard.png)

## 이 프로토타입이 보여주려는 것

기록이 작성됐다는 사실과 *필요한 일이 실제로 처리됐다*는 사실은 다릅니다. PawCare는 이 둘을 분리해서 다룹니다.

> 가설(사용자 조사로 검증된 사실이 아님): 돌봄 정보가 메신저·구두 전달에 흩어지면, 다음 담당자가 확인했는지, 실제 조치가 끝났는지 알기 어렵다.

| 질문 | PawCare의 답 |
|---|---|
| 기록이 업무가 되려면? | 기록 저장만으로는 업무가 생기지 않습니다. 직원이 후속 업무를 **직접 승인**해야 합니다. |
| AI는 무엇을 하나? | 기록에서 후속 확인 사항을 **제안**만 합니다. 진단하지 않고, 기록에 없는 사실을 만들지 않으며, 직원이 승인하기 전에는 업무가 아닙니다. |
| 확인했다 = 끝났다? | 아닙니다. **확인 상태**(`pending` / `acknowledged`)와 **조치 상태**(`todo` / `in_progress` / `completed`)는 별개이며, 조치 완료에는 실제 조치 결과 입력이 필요합니다. |
| 보호자에게는? | 직원이 문구를 검토하고 **공개 승인**한 기록만 보입니다. 내부 메모·인계 내용은 비공개입니다. |

## 시연 흐름

아래 순서가 그대로 실제 버튼 조작으로 진행됩니다. (`tests/capture_screenshots.py`가 이 순서로 화면을 자동 캡처했습니다.)

### 1. 역할 선택 → 직원 대시보드
![역할 선택](docs/screenshots/01-role-select.png)

요약 숫자(돌봄 중, 확인 필요, 진행 중, 완료)는 DB에서 계산됩니다. 업무는 *확인 대기 → 조치 필요 → 진행 중 → 완료* 순서로 정렬되고, 완료된 업무는 일부러 덜 강조합니다. 상태는 색뿐 아니라 아이콘과 텍스트로도 표시합니다.

### 2. 반려견 프로필 · 기록 작성
| 반려견 목록 (검색·필터) | 프로필 (장기 참고사항 / 오늘 기록 / 업무) |
|---|---|
| ![반려견 목록](docs/screenshots/03-dogs.png) | ![반려견 프로필](docs/screenshots/04-dog-profile.png) |

프로필의 *지속적으로 확인해야 할 돌봄 정보*는 오늘의 기록과 구분되며, AI가 자동으로 바꾸지 않습니다.

![빠른 기록 작성](docs/screenshots/05-record-form.png)

기록 유형별 선택지로 빠르게 남깁니다. 선택한 값만으로 건강 이상을 판단하지 않습니다.

### 3. AI 후속 업무 제안 (직원이 검토·확정)
![AI 제안](docs/screenshots/06-ai-suggestion.png)

*기록에 있는 사실*과 *제안한 행동*을 나눠 보여주고, 근거 문장을 원문 그대로 인용합니다. **업무로 등록 / 수정하기 / 제안 무시** 중 직원이 고릅니다. API 키가 없으면 "데모 분석(규칙 기반 · 실제 AI 아님)"이라고 표시합니다.

### 4. 담당자 인계 → 확인 → 조치
| 오전 담당자로 열람 | 오후 담당자로 전환해 확인 완료 |
|---|---|
| ![확인 대기](docs/screenshots/07-task-pending-as-morning.png) | ![확인 완료, 조치 필요 유지](docs/screenshots/08-task-acknowledged.png) |

담당자가 아니면 처리 버튼이 잠기고 이유가 표시됩니다. 오른쪽에서 확인 완료가 되어도 **조치 상태는 "조치 필요" 그대로**입니다.

![조치 완료](docs/screenshots/09-task-completed.png)

조치 결과를 입력해야 완료할 수 있고, 완료 시각과 변경 이력이 남습니다.

### 5. 모든 화면에 같은 상태가 반영
| 대시보드 | 업무 인계 목록 |
|---|---|
| ![대시보드 갱신](docs/screenshots/10-dashboard-after.png) | ![업무 인계 목록](docs/screenshots/11-task-handoff-list.png) |

### 6. 보호자 미리보기 · 모바일
| 보호자 미리보기 (승인된 문구만) | 모바일 폭 |
|---|---|
| ![보호자 미리보기](docs/screenshots/12-parent-preview.png) | ![모바일](docs/screenshots/13-mobile-dashboard.png) |

보호자 화면은 미리보기일 뿐이며 실제로 전송되지 않습니다.

### 7. 오늘의 일과와 인계 시점
| 대시보드의 일과 구간 | 구간별 기록 현황 |
|---|---|
| ![대시보드 일과](docs/screenshots/14-dashboard-routine.png) | ![점심·휴식 구간](docs/screenshots/15-routine-lunch.png) |

유치원의 하루를 구간(등원 → 오전 교육 → 점심·휴식 → 오후 산책 → 그루밍 → 하원)으로 나누고, 기록과 업무를 그 구간에 붙입니다.
- 기록 시각에 맞춰 구간이 자동으로 정해지고(직접 바꿀 수 있음), 구간에서 바로 기록을 작성할 수 있습니다.
- **이 구간에 아직 기록이 없는 반려견**이 위에 올라와 빠뜨린 기록을 찾기 쉽습니다.
- **인계 시점**(오전 → 오후 담당자)에서는 이어받을 일(확인 대기 / 조치 필요 / 진행 중)과 그 업무 목록을 한 화면에서 처리합니다.

![인계 시점](docs/screenshots/16-routine-handoff.png)

구간 이름과 프로그램은 일반적인 예시 템플릿이며 편집 기능은 아직 없습니다. 영업시간 밖에는 오늘 가장 최근에 기록이 있는 구간을 보여줍니다.

### 8. 새 반려견 등록과 프로필 사진
| 원형 가이드로 사진 자르기 | 등록 폼 | 등록된 프로필 |
|---|---|---|
| ![사진 자르기](docs/screenshots/17-photo-cropper.png) | ![등록 폼](docs/screenshots/18-register-dog.png) | ![새 프로필](docs/screenshots/19-new-dog-profile.png) |

사진은 **어떤 비율이든 올릴 수 있고**, 브라우저에서 원형 가이드 안의 위치·확대를 맞춰 **512×512 정사각형**으로 잘라 보냅니다(드래그, 휠·슬라이더 확대, 키보드 이동 지원). 서버는 파일 형식(앞부분 시그니처까지)과 용량(1MB)을 검사하고, 올린 사진은 Git에 올라가지 않는 `uploads/`에 저장합니다.

## 실행 방법

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload      # http://localhost:8000
```

- 첫 실행 시 `pawcare.db`(SQLite)가 만들어지고 샘플 데이터가 자동 등록됩니다.
- 화면 왼쪽 아래 **데모 데이터 초기화**로 처음 상태로 되돌릴 수 있습니다.
- 상단의 **시연 담당자** 드롭다운으로 오전/오후 담당자·관리자를 전환합니다. (로그인 대체)

### AI 연동 (선택)

비워 두면 규칙 기반 **데모 분석**으로 동작합니다. Gemini를 쓰려면 본인 컴퓨터에서 아래 순서로 설정합니다. **`.env`는 Git에 올라가지 않으며(`.gitignore`), 키는 서버에서만 쓰이고 프런트엔드로 전달되지 않습니다.**

1. `.env` 만들기 (프로젝트 맨 위 폴더에서)
   ```bash
   cp .env.example .env          # Windows 명령 프롬프트: copy .env.example .env
   ```
2. `.env`에 키를 입력합니다. 따옴표·공백 없이 입력합니다.
   ```
   GEMINI_API_KEY=발급받은키
   GEMINI_MODEL=
   ```
3. 내 키로 쓸 수 있는 모델 이름을 확인합니다. (모델 이름은 자주 바뀌므로 목록에서 고르세요)
   ```bash
   python -m backend.list_models
   ```
   출력된 이름 중 하나(★ 표시된 flash 계열 권장)를 `GEMINI_MODEL=`에 그대로 붙여 넣습니다.
4. 서버를 (다시) 실행합니다. `.env`를 고쳤다면 반드시 껐다 켜야 합니다.
   ```bash
   python -m uvicorn backend.main:app --reload
   ```
5. 확인: `http://localhost:8000/api/health`가 `"ai_configured": true`이고, AI 제안 화면 라벨이 **"Gemini 분석 (모델명)"** 이면 성공입니다.
   "데모 분석" 라벨과 함께 안내문이 보이면 호출이 실패해 데모 분석으로 대체된 것입니다(키·모델명·네트워크 확인).

모델 응답은 그대로 쓰지 않고 검증합니다. 원본 기록에 없는 근거 문장이 있거나 진단·투약 표현이 있는 제안은 버립니다.

## 구조

```
backend/    FastAPI + SQLite
            database.py  schemas.py  deps.py  seed.py
            routes/      dogs · records · tasks · ai · routine · misc
            services/    ai_service.py (데모 분석 + Gemini + 출력 검증)
            list_models.py  내 키로 쓸 수 있는 Gemini 모델 목록 출력
frontend/   Vanilla JS(ES modules) SPA, 직접 작성한 CSS (Ivory · Sage · Forest Ink · Clay)
            assets/dogs/  샘플 반려견 프로필 사진(더미). 사진이 없거나 불러오지 못하면 이니셜 아바타로 대체
            js/cropper.js  사진 선택·원형 가이드 크롭(라이브러리 없음)
tests/      pytest(API) · e2e_scenario.py(브라우저) · capture_screenshots.py
docs/       시연 화면 캡처
```

**데이터 모델:** `organizations`, `staff`, `dogs`(사진 경로 포함), `routine_blocks`(일과 구간), `care_records`(보호자 공개 상태·구간 포함), `tasks`(`source_record_id`로 원본 기록 연결), `task_action_logs`. 기존 DB는 시작할 때 자동으로 마이그레이션됩니다.
모든 데이터는 `org_id`(유치원)로 분리되어, 다른 유치원 직원은 접근할 수 없습니다.

**주요 API**

| | |
|---|---|
| `GET /api/dashboard` | 요약 숫자와 정렬된 업무 목록 |
| `GET/POST /api/dogs` · `GET/PATCH /api/dogs/{id}` | 목록(검색·상태 필터)·등록, 상세·프로필 수정 |
| `POST/DELETE /api/dogs/{id}/photo` | 프로필 사진 업로드(JPG·PNG·WebP, 1MB 이하)·삭제 |
| `GET /api/routine` · `GET /api/routine/{id}` | 일과 구간과 기록 현황, 구간 상세·인계 요약 |
| `GET/POST /api/records` | 기록 조회·생성 |
| `PATCH /api/records/{id}/parent-approval` | 보호자 공개 승인/취소 |
| `GET/POST /api/tasks` · `GET/PATCH /api/tasks/{id}` | 업무 조회·생성·담당자/내용 변경 |
| `POST /api/tasks/{id}/actions` | `acknowledge` · `start` · `complete`(결과 필수) · `comment` |
| `POST /api/ai/suggest-tasks` | 제안 반환(저장하지 않음) |

현재 직원은 `X-Staff-Id` 헤더로 식별합니다(데모용). 오류는 한국어 메시지와 필드별 `errors`로 반환합니다.

## 테스트

```bash
python -m pytest -q                     # API·규칙·업로드 보안·일과·마이그레이션 26개
pip install playwright                  # e2e 및 캡처에 필요
python tests/e2e_scenario.py            # 서버 실행 후. 실제 브라우저로 전체 시나리오 검증
python tests/capture_screenshots.py     # docs/screenshots 재생성
```

e2e(19개 항목)는 샘플 데이터를 초기화한 뒤 기록 저장, AI 제안 무시/수정/승인, 담당자 전환, 확인·조치 분리, 새로고침 후 데이터 유지, 입력 오류, 없는 ID 처리, 보호자 미리보기, 반려견 등록과 사진 크롭(드래그한 위치가 결과물 픽셀에 반영되는지까지), 일과 구간, 유치원 간 격리, 390px 가로 스크롤 없음, 콘솔 오류 없음을 확인합니다.

## 다음 계획

보호자에게 사진을 전달하는 알림장(로그인 포함)은 [docs/PLAN-parent-sharing.md](docs/PLAN-parent-sharing.md)에 단계별 계획으로 정리했습니다. **아직 구현되지 않았습니다.**

## 한계

- **로그인·회원가입 없음.** `org_id` 분리와 `X-Staff-Id` 의존성이 실제 인증으로 바뀔 자리입니다.
- **Gemini 실제 호출은 검증하지 못했습니다.** 개발 환경에 키가 없어, 출력 검증 로직과 실패 시 데모 분석으로의 대체 동작만 테스트했습니다.
- 푸시/카카오 알림, 예약·결제, 음성, CCTV, 의료 연동, 실시간 다중 사용자 동기화는 범위 밖입니다. 상단 알림 아이콘은 내게 배정된 확인 대기 업무 수를 보여줄 뿐 실제 푸시가 아닙니다.
- 보호자 화면은 승인된 기록 미리보기까지입니다. 시각은 한국 표준시(KST) 기준입니다.
- 샘플 반려견 사진은 시연용 더미 이미지입니다. 직접 올린 사진은 서버 디스크(`uploads/`)에 저장되며, 파일명이 무작위일 뿐 **로그인 없이 주소를 알면 열 수 있습니다.** 실제 서비스에서는 인증과 객체 저장소가 필요합니다. 영상 업로드는 아직 없습니다.
- 일과 구간은 예시 템플릿 하나이며 편집·요일별 설정은 없습니다. 반려견 삭제 기능도 아직 없습니다.
- 샘플 데이터의 "알레르기·민감성" 등은 시연용 가상 정보이며 실제 건강 정보가 아닙니다.

# EV 충전 최적 시간 추천 — 백엔드

2026-04-16 시행 전기차 충전전력요금 기준으로 **가장 싸게 충전할 수 있는 시간**을
추천하는 API.
빛가람 AI·ICT 경진대회 출품작.

명세: 노션 [기능 명세서](https://app.notion.com/p/3e2c8fd1afc981d0a00ef5fdcec314f1) ·
[API 명세서](https://app.notion.com/p/3e2c8fd1afc981b38befc694478b0e72) ·
[백엔드 설계서](https://app.notion.com/p/3e2c8fd1afc98110bbc5ecc42b8a35cd)

## 빠른 시작

```bash
# uv가 없다면
curl -LsSf https://astral.sh/uv/install.sh | sh

docker compose up -d db          # PostgreSQL 17
cd backend
uv sync                          # Python 3.13 + 의존성
uv run alembic upgrade head      # 테이블 생성
uv run uvicorn evcharge.main:app --reload
```

- API 문서: http://localhost:8000/docs
- 테스트: `cd backend && uv run pytest`

## 구현 상태

| 엔드포인트 | 기능 | 상태 |
| --- | --- | --- |
| `GET /health` | F-08 요금 확인 상태 | 구현 |
| `POST /api/recommend` | F-01·F-03·F-04 추천·절감액 | 구현 |
| `GET /api/timeline` | F-05·F-06 하루 단가·시뮬레이션 | 구현 |
| `GET /api/chargers` | F-07 주변 충전소 | 구현 |
| `/api/auth/*` | F-11 회원가입·로그인 | 구현 |
| `/api/me/*` | F-12·F-13·F-14 사용자 데이터 | 구현 |
| `GET /api/solar-forecast` | F-09 태양광 예측 | 구현 (키 필요) |
| `POST /api/chat` | F-10 자연어 질의 | 구현 (키 필요) |

**기능 명세의 F-01~F-14가 전부 구현됐다.** 스텁으로 남은 엔드포인트는 없다.

세 엔드포인트는 외부 자격증명이 있어야 동작하고, 없으면 각자 501을 낸다.
키 없이도 나머지 기능은 전부 돈다 — 기동 시점에 막지 않는다.

| 키 | 없으면 501이 되는 곳 | 발급처 |
| --- | --- | --- |
| `CHARGER_API_KEY` | `GET /api/chargers` | [공공데이터포털 15076352](https://www.data.go.kr/data/15076352/openapi.do) |
| `KMA_API_KEY` | `GET /api/solar-forecast` | [공공데이터포털 15084084](https://www.data.go.kr/data/15084084/openapi.do) |
| `GEMINI_API_KEY` | `POST /api/chat` | [Google AI Studio](https://aistudio.google.com/apikey) (무료) |

공공데이터포털은 계정당 인증키를 하나만 주므로 위 두 키는 **같은 문자열**이 된다.
그래도 설정을 따로 두는 이유는 활용신청이 데이터셋별로 따로 승인되기 때문이다 —
"충전소는 되는데 예보는 안 된다"는 상태가 실제로 있다.

## 충전소 캐시 수집 (F-07)

`GET /api/chargers`는 **공공 API를 부르지 않는다.** 전 사용자 공유 캐시
(`charger_cache`)만 읽고, 그 캐시는 아래 명령이 채운다. 개발계정 트래픽이
**하루 1,000건**이라 사용자 요청마다 부르면 즉시 넘치기 때문이다.

```bash
cd backend
uv run python -m evcharge.sync                    # 전체 수집 (4호출, 약 12초)
uv run python -m evcharge.sync --states           # 상태만 갱신 (1호출, 1초 미만)
uv run python -m evcharge.sync --states --period 5   # 최근 5분 변경분만
```

- 먼저 `backend/.env`에 `CHARGER_API_KEY`를 넣어야 한다 (`.env.example` 참고).
  비어 있으면 아무것도 하지 않고 이유를 찍은 뒤 종료 코드 1로 끝나며,
  `GET /api/chargers`는 501을 유지한다.
- 실측(2026-09-21, `zcode=12`): 32,835행 → **충전소 8,112곳**. 상태 갱신은
  `period=10`에 954행.
- cron이나 워커는 붙이지 않았다. 5분마다 상태를 받아도 하루 300건 안쪽이라
  한도 안에 든다.
- 캐시가 비어 있으면 `GET /api/chargers`는 빈 목록이 아니라 **503**으로 답한다
  — "주변에 충전소가 없다"와 "아직 수집하지 않았다"는 다른 말이다.
- 충전기 상태(`stat`)와 종류(`chgerType`)는 **원문 코드 그대로** 내보낸다.
  공식 활용가이드를 아직 확보하지 못했고(실제 데이터에 문서에 없는 `9`가
  5.3% 있다), 추정 매핑은 '사용 가능'이라 적힌 자리로 사용자를 보낸다.

## 자연어 질의 켜기 (F-10)

`POST /api/chat`은 Google Gemini **무료 티어**를 쓴다. 켜는 데 필요한 것은 키 하나다.

1. <https://aistudio.google.com/apikey> 에서 "Create API key" (신용카드 불필요).
2. `backend/.env`에 넣는다:

   ```
   GEMINI_API_KEY=<발급받은 키>
   ```

3. 서버를 다시 띄운다. 끝이다 — 모델 ID(`GEMINI_MODEL`)와 호출 제한은
   기본값이 있고, 바꾸고 싶을 때만 건드리면 된다 (`.env.example` 참고).

`chat_rate_limits` 테이블이 필요하므로 마이그레이션을 아직 안 돌렸다면:

```bash
cd backend && uv run alembic upgrade head
```

동작 방식에서 알아둘 것:

- **모델은 조건 추출에만 쓴다. 답변 문장은 서버가 쓴다.** 금액·시각은
  `compute_recommendation`의 계산 결과를 그대로 넣는다 — 모델이 숫자를 지어낼
  자리를 아예 두지 않기 위해서다. 질문 하나당 API 호출은 정확히 1회다.
- 모델이 낸 값은 필드마다 범위까지 확인하고, 통과하지 못하면 **고치지 않고
  버린다.** 그 항목은 `missing_fields`가 되어 사용자에게 되묻는다 (150%를
  100%로 "고쳐" 주지 않는다).
- 로그인한 사용자에게 **기본 차량**이 있으면 `battery_kwh`·`charger_kw`·`mode`를
  거기서 채운다 (F-12). 기본 차량이 아닌 차는 쓰지 않는다.
- 사용자별 호출 제한은 기본 **60분당 20회**, 초과 시 429. 카운터는 UPSERT
  한 문장으로 원자적으로 올린다 — 병렬 요청으로 우회되지 않는 것을
  `tests/api/test_chat_rate_limit_race.py`가 실제 동시 요청으로 검증한다.
- 실패한 호출도 할당량을 깎는다. 안 그러면 계속 실패시켜 제한을 무료로 우회할 수 있다.

테스트는 **절대 실제 API를 부르지 않는다.** `tests/conftest.py`가 테스트 세션
동안 `GEMINI_API_KEY`를 비워 두고(개발자 `.env`에 진짜 키가 있어도), 가짜
클라이언트를 autouse로 꽂는다.

## 요금 값의 출처와 확인 상태

`backend/config/tariff.yaml`의 근거는 **기후에너지환경부 보도자료 2026-04-14
「낮엔 낮추고 저녁은 높인다」 붙임 3 「전기자동차 충전전력요금 현황」**이다
(2026-04-16 시행). 원본 PDF 두 건을 `backend/config/`에 함께 두었다 —
설정의 `source` 필드가 가리키는 문서다.

- `20260414(mcee-tou).pdf` — 현행 기준
- `20231109(total).pdf` — 한전 「전기요금(종합)」, 개편 전 기준

**개편에서 바뀐 것은 시간대 구분뿐이고 단가는 그대로다.** 붙임 3의 자가소비용
단가 12개가 2023-11-09 요금표와 한 자리도 다르지 않다 (보도자료 본문의 단가
조정은 적용대상이 산업용(을)이다). 시간대는 여름·봄가을이 바뀌었다:

```
중간부하  08–11 · 12–13 · 18–22   →   08–15 · 21–22
최대부하  11–12 · 13–18           →   15–21
```

겨울철은 개편 전후가 같다. 제주는 시간대 구분이 다른데(경부하 22–08,
중간부하 08–16, 최대부하 16–22) 이 서비스는 전남 기준이라 쓰지 않는다.

**10개 항목 중 8개가 확인됐고 2개가 남았다.** 남은 둘은 보도자료가 말하지
않는 값이다: 공공 급속 **기준단가**는 충전사업자가 각자 정하고, 봄·가을 주말
할인의 **일몰 연도**는 어디에도 적혀 있지 않다.

항목마다 `status`(`verified` / `derived` / `unverified`)를 달아두었고,
`/health`와 `/api/recommend` 응답의 `unverified_tariff_items`가 미확인 항목을
그대로 실어 나른다. 목록은 코드가 아니라 YAML을 훑어 만들기 때문에,
공식 요금표를 확보하면 **`tariff.yaml`의 `value`와 `status`만 고치면 된다.**

테스트는 절대 금액이 아니라 불변식(경부하 < 중간부하 < 최대부하, 할인 단가 <
동일 구간 비할인 단가)을 검증하므로, 값을 갈아끼워도 그대로 살아서 회귀를 잡는다.

**단, 시간대 표만은 예외로 절대값을 못 박는다.** 불변식 테스트는 요금표가
바뀌어도 살아남는 대신 **표 자체가 틀린 것은 잡지 못한다.** 실제로 개편 전
표를 현행으로 오인해 쓴 적이 있고 380개가 넘는 테스트가 전부 통과했다.
`tests/domain/test_calendar.py`가 실제 설정의 24시간을 붙임 3에 고정한다 —
표가 또 바뀌면 깨지고, 그때 고칠 것은 기대값이 아니라 출처다.

## 구조

```
backend/src/evcharge/
├── domain/     순수 파이썬 — FastAPI도 DB도 모른다
│   ├── tariff.py     요금표 로더 + 확인상태 스캔
│   ├── calendar.py   계절·공휴일·부하구간 판정   (F-02)
│   ├── pricing.py    시각 → 원/kWh              (F-02)
│   ├── planner.py    최저 비용 구간 탐색         (F-03, F-04)
│   └── geo.py        거리·바운딩 박스            (F-07)
├── api/        라우터·스키마·에러 변환
│   └── chat_service.py   질문 → 조건 추출 → 문장  (F-10)
├── infra/      SQLAlchemy 세션과 모델
│   ├── charger_api.py    공공 충전소 API 호출     (F-07)
│   ├── charger_sync.py   응답 → 공유 캐시         (F-07)
│   └── llm.py            Gemini 호출기            (F-10)
└── sync.py     `python -m evcharge.sync` 수집 진입점
backend/config/  tariff.yaml · holidays.yaml
```

요금 계산이 이 프로젝트에서 가장 자주 바뀌고 가장 검증이 필요한 부분이라
순수 함수로 떼어놨다. 도메인 테스트는 서버도 DB도 띄우지 않고 돈다.

`planner`는 요금표를 모른다 — "시각 → 단가" 함수 하나만 받는다.

## 알려진 공백

- 공공 급속 **기준단가** 미확인. 충전사업자가 각자 정하는 값이라 하나의 공식 단가가
  없다 — 요청의 `public_base_price`로 주입받는 구조를 유지한다
- 봄·가을 주말 할인의 **일몰 연도** 미확인. 할인 자체(11–14시 50%)는 기후에너지환경부
  보도자료로 확인됐지만 언제까지인지는 어디에도 없다. 기능 명세서만 2030년이라고 해서
  `weekend_discount_sunset`으로 따로 떼어 미확인으로 남겼다
- `config/holidays.yaml`의 음력·대체공휴일은 공공데이터포털 특일 정보 API로 대조 필요
- `tariff_version`은 근거 문서 시행일로 매긴다(`2026.04.16-mcee`). 개정 시 함께 올린다
- 충전소 `status`(`stat`)·충전기 종류(`chgerType`) 코드의 뜻 (원본 활용가이드 확보 후).
  지금은 원문 코드를 그대로 내보낸다. 급속·완속 구분은 코드가 아니라 `capacity_kw`로
  가른다 — `chgerType=04`가 7~350 kW에 걸쳐 있어 코드로는 못 가른다. 커넥터 종류
  (DC차데모/AC완속/DC콤보)는 대체할 필드가 없어 그 표가 있어야 표시할 수 있다
- 지역별 태양광 설비용량 (전력거래소). 없으면 `/api/solar-forecast`의 `predicted_mwh`가
  null로 나간다 — 일사량과 STC 대비 지수는 설비용량과 무관하게 항상 채워진다
- `SKY=2`와 `PTY=2·3`은 실제 예보에서 관찰되지 않아 미검증이다. 나오면 조용히 넘어가지
  않고 예외로 터진다 (`domain/solar.py`의 `SKY_OCTAS`)

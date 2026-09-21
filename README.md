# EV 충전 최적 시간 추천 — 백엔드

한전 현행 전기요금 기준으로 **가장 싸게 충전할 수 있는 시간**을 추천하는 API.
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
| `GET /api/solar-forecast` | F-09 태양광 예측 | 501 스텁 |
| `POST /api/chat` | F-10 자연어 질의 | 501 스텁 |

스텁도 경로·메서드·스키마는 명세대로 선언돼 있어 `/docs`에서 전체 계약을 볼 수 있다.

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

## 요금 값의 출처와 확인 상태

`backend/config/tariff.yaml`의 요금 값은 한국전력공사 「전기요금(종합)」
**2023년 11월 9일 시행**본에서 옮긴 것이다. 원본 PDF를 `backend/config/`에
함께 두었다 — 설정의 `source` 필드가 가리키는 문서다.
2026-09-21 기준 이후 개정판이 없어 이것이 현행 요금표다.

**9개 항목 중 6개가 확인됐고 3개가 남았다.** 남은 셋은 이 문서가 정하지 않는
값들이다: 공공 급속 단가는 충전사업자가 각자 정하고, 봄·가을 주말 할인
(EV 충전 특례할인)은 별도 고시다.

항목마다 `status`(`verified` / `derived` / `unverified`)를 달아두었고,
`/health`와 `/api/recommend` 응답의 `unverified_tariff_items`가 미확인 항목을
그대로 실어 나른다. 목록은 코드가 아니라 YAML을 훑어 만들기 때문에,
공식 요금표를 확보하면 **`tariff.yaml`의 `value`와 `status`만 고치면 된다.**

테스트는 절대 금액이 아니라 불변식(경부하 < 중간부하 < 최대부하, 할인 단가 <
동일 구간 비할인 단가)을 검증하므로, 값을 갈아끼워도 그대로 살아서 회귀를 잡는다.

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
├── infra/      SQLAlchemy 세션과 모델
│   ├── charger_api.py    공공 충전소 API 호출     (F-07)
│   └── charger_sync.py   응답 → 공유 캐시         (F-07)
└── sync.py     `python -m evcharge.sync` 수집 진입점
backend/config/  tariff.yaml · holidays.yaml
```

요금 계산이 이 프로젝트에서 가장 자주 바뀌고 가장 검증이 필요한 부분이라
순수 함수로 떼어놨다. 도메인 테스트는 서버도 DB도 띄우지 않고 돈다.

`planner`는 요금표를 모른다 — "시각 → 단가" 함수 하나만 받는다.

## 알려진 공백

- 공공 급속 단가와 봄·가을 주말 할인 미확인 (한전 요금표가 정하지 않는 값 — 사업자 단가표와 EV 충전 특례할인 고시 필요)
- `config/holidays.yaml`의 음력·대체공휴일은 공공데이터포털 특일 정보 API로 대조 필요
- `tariff_version`은 요금표 시행일로 매긴다(`2023.11.09-kepco`). 개정 시 함께 올린다
- 충전소 `status`(`stat`)·충전기 종류(`chgerType`) 코드의 뜻 (원본 활용가이드 확보 후).
  지금은 원문 코드를 그대로 내보내고 화면이 모르는 코드를 원문 표시한다 —
  프론트의 급속/완속 필터는 그 표가 확정돼야 값을 맞출 수 있다

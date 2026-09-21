# EV 충전 최적 시간 추천 — 백엔드

2026년 개편 전기요금 기준으로 **가장 싸게 충전할 수 있는 시간**을 추천하는 API.
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
| `GET /api/chargers` | F-07 주변 충전소 | 501 스텁 |
| `/api/auth/*` | F-11 회원가입·로그인 | 501 스텁 |
| `/api/me/*` | F-12·F-13·F-14 사용자 데이터 | 501 스텁 |
| `GET /api/solar-forecast` | F-09 태양광 예측 | 501 스텁 |
| `POST /api/chat` | F-10 자연어 질의 | 501 스텁 |

스텁도 경로·메서드·스키마는 명세대로 선언돼 있어 `/docs`에서 전체 계약을 볼 수 있다.
테이블 5개와 마이그레이션은 준비돼 있으나 아직 어느 라우터도 쓰지 않는다.

## ⚠️ 요금 값은 잠정치다

`backend/config/tariff.yaml`의 요금 값은 **한전 공식 요금표를 확보하기 전의 잠정치**다.
계산은 정상적으로 돌아가지만 **금액은 실제 요금이 아니다.**

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
│   └── planner.py    최저 비용 구간 탐색         (F-03, F-04)
├── api/        라우터·스키마·에러 변환
└── infra/      SQLAlchemy 세션과 모델
backend/config/  tariff.yaml · holidays.yaml
```

요금 계산이 이 프로젝트에서 가장 자주 바뀌고 가장 검증이 필요한 부분이라
순수 함수로 떼어놨다. 도메인 테스트는 서버도 DB도 띄우지 않고 돈다.

`planner`는 요금표를 모른다 — "시각 → 단가" 함수 하나만 받는다.

## 알려진 공백

- 요금표 전 항목 미확인 (한전 공식 요금표 필요)
- `config/holidays.yaml`의 음력·대체공휴일은 공공데이터포털 특일 정보 API로 대조 필요
- `tariff_version` 을 언제 어떻게 올릴지 미정
- 인증 토큰 만료·갱신 방식, 로그인 실패 제한 수치 미정
- 충전소 `status` 코드 매핑 (원본 API 문서 확인 후)

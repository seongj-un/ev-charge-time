# EV 충전 최적 시간 추천 — 프론트엔드

2026년 개편 전기요금 기준으로 **가장 싸게 충전할 수 있는 시간**을 보여주는 반응형 웹.
빛가람 AI·ICT 경진대회 출품작.

설계: [프론트엔드 설계서](../docs/superpowers/specs/2026-09-21-frontend-design.md) ·
명세: 노션 [기능 명세서](https://app.notion.com/p/3e2c8fd1afc981d0a00ef5fdcec314f1) ·
[API 명세서](https://app.notion.com/p/3e2c8fd1afc981b38befc694478b0e72)

## 빠른 시작

백엔드를 먼저 띄운다 (다른 터미널):

```bash
cd ../backend
uv sync
uv run uvicorn evcharge.main:app --reload
```

그다음:

```bash
npm install
npm run dev          # http://localhost:3000
```

백엔드가 다른 주소에 있으면 `BACKEND_URL`로 바꾼다:

```bash
BACKEND_URL=http://192.168.0.10:8000 npm run dev
```

| 명령 | 하는 일 |
| --- | --- |
| `npm run dev` | 개발 서버 |
| `npm test` | 테스트 (vitest) |
| `npm run typecheck` | 타입 검사 |
| `npm run build` | 프로덕션 빌드 |

## 화면

| 화면 | 경로 | 상태 |
| --- | --- | --- |
| 홈 | `/` | 구현 |
| 충전 조건 입력 | `/recommend` | 구현 |
| 추천 결과 | `/recommend/result` | 구현 |
| 하루 단가 | `/timeline` | 구현 |
| 주변 충전소 | `/stations` | 준비 중 (백엔드 501) |
| 로그인·회원가입·내 정보 | `/login` `/signup` `/me` | 준비 중 |

준비 중 화면은 빈 골격과 사유만 둔다. 가짜 데이터를 채우지 않는다 —
시연에서 없는 기능이 있는 것처럼 보이면 질문 한 번에 무너진다.

## ⚠️ 화면의 금액은 잠정치다

백엔드 `config/tariff.yaml`의 요금 값이 한전 공식 요금표 확보 전의 잠정치다.
계산은 정상이지만 **금액은 실제 요금이 아니다.**

백엔드가 응답마다 `unverified_tariff_items`를 실어 보내고, 프론트는 이 배열이
비어 있지 않으면 **항상** 고지 배너를 띄운다. 이 배너를 조건부로 숨기지 마라 —
잠정 금액이 확정 금액처럼 보인다.

## 알아둘 것 세 가지

### 백엔드는 rewrite로 넘어간다

`next.config.ts`가 `/api/*`와 `/health`를 백엔드로 넘긴다. 브라우저 입장에선
동일 출처라 CORS 설정이 필요 없고 httpOnly 쿠키가 그냥 실린다.
그래서 API를 부를 땐 `http://localhost:8000/...`이 아니라 `/api/...`로 쓴다.

### 시각에 Date를 쓰지 마라

백엔드는 시각을 항상 `+09:00`으로 주고받는다. `new Date(...)`로 만들어
`toLocaleString`에 넘기면 브라우저 표준시로 다시 읽혀 9시간 어긋난다.
`lib/format.ts`의 `formatHm` · `formatKoreanDate`를 쓴다.

요청을 만들 때도 `toISOString()`을 쓰지 않는다 — UTC로 바뀐다.
`lib/recommend-params.ts`의 `toLocalInput`이 `"2026-10-07T18:00"` 형식을 만든다.

### 색을 새로 만들지 마라

`app/globals.css`의 `@theme`에 있는 토큰만 쓴다. 값은 화면 디자인 PDF의 픽셀에서
직접 뽑았다. 부하구간 색 두 개는 흰 배경 대비가 3:1 아래라, 차트는 색만으로
정보를 주지 않고 범례·막대 레이블·표가 같은 정보를 글자로 나른다.
차트를 고칠 때 이 셋 중 하나를 빼지 마라.

## 구조

```
src/
├── app/          라우트. 각 화면은 PageContainer로 감싼다
├── components/
│   ├── shell/    AppShell · TopNav(데스크톱) · TabBar(모바일)
│   ├── ui/       Button · Card · Badge · Field · SegmentedControl · Notice
│   └── chart/    PriceBarChart — 하루 단가와 추천 결과가 공유한다
└── lib/
    ├── api/      types(백엔드 스키마 1:1) · client · endpoints
    ├── format.ts         원·kWh·시각 포맷
    ├── charging.ts       필요 충전량·소요시간·구간 시각
    └── recommend-params.ts  URL 쿼리 ↔ 폼 ↔ 요청
```

충전 조건은 URL 쿼리로 넘긴다. 결과 화면에서 새로고침·뒤로가기·링크 공유가
그냥 되고, 시연에서 링크 하나로 특정 추천을 바로 띄울 수 있다.

## 테스트

절대 금액을 단언하지 않는다 — 요금표가 확정되면 전부 바뀐다. 대신 불변식을 본다:
막대 높이가 단가에 비례하는가, 할인 없는 날에 할인 배너가 안 뜨는가,
목표 충전량이 현재보다 낮으면 요청이 안 나가는가.

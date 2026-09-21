# 프론트엔드 설계 — EV 충전 최적 시간 추천

2026-09-21 · 대상: `frontend/` · 근거: 화면 디자인 PDF 27장, 노션 [기능 명세서](https://app.notion.com/p/3e2c8fd1afc981d0a00ef5fdcec314f1) · [API 명세서](https://app.notion.com/p/3e2c8fd1afc981b38befc694478b0e72)

## 무엇을 만드는가

충전 조건을 넣으면 가장 싼 시간을 알려주는 반응형 웹. 디자인 PDF는 모바일 13화면과
데스크톱 12화면을 모두 그려 두었다. **이번 범위는 백엔드가 실제로 도는 네 화면이다.**

| 화면 | 경로 | 쓰는 API | 상태 |
| --- | --- | --- | --- |
| 홈 | `/` | 없음 (정적) | 구현 |
| 충전 조건 입력 | `/recommend` | 없음 (제출 시 이동) | 구현 |
| 추천 결과 | `/recommend/result` | `POST /api/recommend`, `GET /api/timeline` | 구현 |
| 하루 단가 | `/timeline` | `GET /api/timeline` | 구현 |
| 주변 충전소 | `/stations` | `GET /api/chargers` | 준비 중 (백엔드 501) |
| 로그인·회원가입·내 정보 | `/login` `/signup` `/me` | `/api/auth/*` `/api/me/*` | 준비 중 (미병합·501) |

준비 중 화면은 **빈 골격과 사유**만 둔다. 가짜 데이터를 채우지 않는다 —
시연에서 없는 기능이 있는 것처럼 보이면 질문 한 번에 무너진다.

## 스택

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · Vitest + Testing Library.
노션 기술 스택 문서가 Next.js(반응형 웹, PWA)로 정해 둔 것을 따른다.

## 확정한 결정 네 가지

### 1. 백엔드는 rewrite로 넘긴다

백엔드 `main.py`에 CORS 미들웨어가 없고, 인증이 httpOnly 쿠키다. 브라우저가
`localhost:3000 → :8000`을 직접 치면 교차 출처라 둘 다 걸린다.

`next.config.ts`의 rewrites로 `/api/*`와 `/health`를 넘기면 브라우저 입장에선
동일 출처다. 쿠키가 손대지 않아도 실리고, **백엔드 코드를 건드릴 필요가 없다** —
지금 백엔드는 `review-notion-ev-charge` 브랜치에 있고 main에 없다.

백엔드 주소는 `BACKEND_URL` 환경변수로 바꾼다 (기본 `http://localhost:8000`).

### 2. 시각은 Date를 거치지 않는다

백엔드는 시각을 항상 `+09:00`을 달아 보내고, 표준시 없는 입력을 KST로 읽는다
(API 명세서 1장). 프론트에서 `new Date(...)`로 만들어 `toLocaleString`에 넘기면
브라우저 표준시로 다시 읽힌다. 심사위원 노트북이 어느 표준시든 "22:00 추천"은
22:00으로 보여야 한다.

그래서 `lib/format.ts`의 `parseKstWallClock`이 ISO 문자열에 적힌 벽시계 값을
정규식으로 그대로 꺼낸다. 요청을 만들 때도 `toISOString()`을 쓰지 않는다 —
UTC로 바뀌어 9시간 어긋난 추천이 돌아온다.

### 3. 충전 조건은 URL 쿼리로 넘긴다

입력 화면과 결과 화면이 서로 다른 라우트다. 조건을 전역 상태에 두면 결과 화면에서
새로고침하는 순간 빈 화면이 된다. URL에 실으면 새로고침·뒤로가기·링크 공유가
공짜로 따라오고, 시연에서 링크 하나로 특정 추천을 바로 띄울 수 있다.

쿼리 이름은 백엔드 요청 필드와 똑같이 쓴다 (`battery_kwh`, `soc_now`, …) —
URL만 보고도 무슨 요청이 나갈지 안다. 계약은 `lib/recommend-params.ts`에
테스트로 고정되어 있다.

### 4. 차트는 직접 그린다

디자인이 구체적이다. 시간별 부하구간 색, 막대 위에 겹치는 두 줄 마커(추천 · 지금 바로),
둥근 상단, 그리고 축이 24시간(하루 단가)과 14시간(추천 결과, 18시→다음날 08시)
두 가지다. 차트 라이브러리로 이걸 맞추는 게 직접 그리는 것보다 길다.

`components/chart/PriceBarChart.tsx` 하나를 두 화면이 공유한다. 컬럼 배열을
통째로 받으므로 축이 0시에서 시작하지 않아도 된다.

**막대 높이는 0을 바닥으로 단가에 비례한다.** 축을 자르면 62.5원과 125.1원이
몇 배 차이처럼 보인다 — 절감액을 주장하는 화면에서 그건 과장이다.

## 디자인 토큰

PDF 픽셀에서 직접 뽑아 `app/globals.css`의 `@theme`에 넣었다. **새 색을 만들지 않는다.**

| 역할 | 값 | 쓰이는 곳 |
| --- | --- | --- |
| `canvas` | `#F1F0EB` | 페이지 배경 |
| `surface` | `#FEFEFE` | 카드 |
| `sunken` | `#E6E3DC` | 세그먼티드 트랙, 지도 자리 |
| `field` | `#FAF9F5` | 입력 필드 |
| `line` | `#D9D9D5` | 테두리 |
| `ink` / `ink-2` / `ink-3` | `#16171B` / `#4B4C50` / `#7C7D80` | 본문 / 보조 / 각주 |
| `brand` | `#0C5949` | 주 버튼, 활성 탭 |
| `accent` | `#C4DE3C` | 절감액, 주말 할인 |
| `band-light` / `band-middle` / `band-peak` | `#2F7C5A` / `#C88918` / `#B7422E` | 경부하 / 중간 / 최대 |
| `ok` / `warn` / `off` | `#E2EFE6`·`#275742` / `#F6EAD0`·`#644303` / `#E6E3DC`·`#55565B` | 상태 배지 |

다크 모드는 넣지 않는다. 디자인에 없고, 부하구간 색 3개는 어두운 배경에서 대비가
무너져 별도 팔레트를 새로 정해야 한다.

### 색만으로 정보를 주지 않는다

부하구간 팔레트를 검증한 결과: 색맹 분리는 통과(ΔE 12.5 protan / 15.7 tritan),
**대비는 두 색이 3:1 아래다** (중간부하 2.95:1, 주말 할인 1.5:1). 디자인 확정색이라
바꾸지 않되, 같은 정보를 글자가 함께 나른다.

- 범례가 차트와 항상 같이 있다
- 막대마다 `aria-label`로 "18시 · 최대 · 132.0원/kWh"가 읽힌다
- 같은 데이터가 숨은 `<table>`로도 들어 있다
- 하루 단가 화면은 밴드별 단가 목록을 화면에 직접 띄운다

## 구조

```
frontend/src/
├── app/
│   ├── layout.tsx                 폰트·셸
│   ├── page.tsx                   홈
│   ├── recommend/page.tsx         충전 조건 입력
│   ├── recommend/result/page.tsx  추천 결과
│   ├── timeline/page.tsx          하루 단가
│   ├── {stations,me,login,signup}/page.tsx   준비 중
│   ├── manifest.ts                PWA
│   └── globals.css                디자인 토큰
├── components/
│   ├── shell/    AppShell · TopNav(데스크톱) · TabBar(모바일) · nav · icons
│   ├── ui/       Button · Card · Badge · Field · SegmentedControl · Notice
│   ├── chart/    PriceBarChart · BandLegend · bands
│   ├── recommend/  입력 폼
│   ├── result/     추천 결과
│   └── timeline/   하루 단가
└── lib/
    ├── api/      types(백엔드 스키마 1:1) · client · endpoints
    ├── format.ts     원·kWh·시각 포맷
    ├── charging.ts   필요 충전량·소요시간·구간 시각
    └── recommend-params.ts   URL 쿼리 ↔ 폼 ↔ 요청
```

`lib/api/types.ts`는 필드 이름을 snake_case 그대로 둔다. camelCase로 바꾸면 응답을
볼 때마다 두 이름을 머릿속에서 번역해야 하고, 그 번역 계층이 틀려도 타입 검사가
잡아주지 못한다.

## 오류 처리

FastAPI는 오류를 두 모양으로 보낸다 (API 명세서 1장). 업무 오류는 `detail`이 문자열,
필드 검증 실패는 배열이다. 화면마다 이 분기를 풀면 같은 코드가 네 군데 생기므로
`lib/api/client.ts`의 `messageFromDetail`이 한 곳에서 문장으로 만든다.

`ApiError`는 `status`와 함께 `notImplemented`(501)·`needsLogin`(401)을 노출한다.
`status === 0`은 서버에 닿지 못한 경우로, "백엔드가 실행 중인지 확인하세요"로 바꿔 준다 —
원래 메시지 "fetch failed"는 사용자에게 아무것도 알려주지 않는다.

## 요금이 잠정치라는 사실을 숨기지 않는다

`tariff.yaml`의 값은 한전 공식 요금표 확보 전의 잠정치고, 백엔드가 응답마다
`unverified_tariff_items`를 실어 보낸다. 프론트는 이 배열이 비어 있지 않으면
**항상** 고지 배너를 띄운다. 조건부로 숨기면 잠정 금액이 확정 금액처럼 보인다.

`assumptions` 배열("충전 출력 일정 · 연속 충전 · 기본요금 제외")도 결과 화면에 적는다.

## 테스트

순수 함수는 TDD로 먼저 쓴다 — `format`, `charging`, `recommend-params`,
`api/client`. 컴포넌트는 렌더 + 핵심 상호작용, `fetch`는 `vi.stubGlobal`로 모킹한다.

절대 금액을 단언하지 않는다. 요금표가 확정되면 전부 바뀐다. 대신 불변식을 본다 —
막대 높이가 단가에 비례하는가, 할인 없는 날에 할인 배너가 안 뜨는가,
목표 충전량이 현재보다 낮으면 요청이 안 나가는가.

## 남은 공백

- 주변 충전소·인증·차량·충전 기록·즐겨찾기 화면 (백엔드 501 또는 미병합)
- PWA 아이콘 에셋 없음 — manifest의 `icons`가 비어 있다
- 서비스 이름 미정. `components/shell/nav.ts`의 `SERVICE_NAME` 한 곳만 고치면 된다
- 태양광 발전 예측 겹쳐 보기 (F-09, 백엔드 501)

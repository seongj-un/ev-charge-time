---
version: alpha
name: Kinetic — charging clarity
description: Existing Korean-first identity with the user-approved deep navy primary and lime accent, redesigned for readable charging decisions.
colors:
  primary: "#243A5E"
  on-primary: "#FEFEFE"
  accent: "#C4DE3C"
  on-accent: "#16171B"
  background: "#F1F0EB"
  on-background: "#16171B"
  surface: "#FEFEFE"
  on-surface: "#16171B"
  sunken: "#E6E3DC"
  on-sunken: "#4B4C50"
  field: "#FAF9F5"
  on-field: "#16171B"
  border: "#D9D9D5"
  muted: "#4B4C50"
  tertiary: "#7C7D80"
  inverse: "#16171B"
  on-inverse: "#FEFEFE"
  ring: "#243A5E"
  band-light: "#2F7C5A"
  band-middle: "#C88918"
  band-peak: "#B7422E"
  ok: "#E2EFE6"
  on-ok: "#275742"
  warning: "#F6EAD0"
  on-warning: "#644303"
  off: "#E6E3DC"
  on-off: "#55565B"
  danger: "#B7422E"
  on-danger: "#FEFEFE"
typography:
  display:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: 56px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  section:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: 20px
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
  small:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
  number:
    fontFamily: "ui-monospace, SF Mono, JetBrains Mono, Menlo, monospace"
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1.2
rounded:
  sm: 8px
  md: 12px
  lg: 20px
  pill: 999px
spacing:
  base: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 64px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    height: 48px
    padding: "{spacing.md}"
  button-primary-hover:
    backgroundColor: "{colors.inverse}"
    textColor: "{colors.on-inverse}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    height: 48px
  field:
    backgroundColor: "{colors.field}"
    textColor: "{colors.on-field}"
    rounded: "{rounded.md}"
    height: 48px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  card-inverse:
    backgroundColor: "{colors.inverse}"
    textColor: "{colors.on-inverse}"
    rounded: "{rounded.lg}"
  savings:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.lg}"
  nav-active:
    backgroundColor: "{colors.background}"
    textColor: "{colors.primary}"
    rounded: "{rounded.md}"
  badge-ok:
    backgroundColor: "{colors.ok}"
    textColor: "{colors.on-ok}"
  badge-warning:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.on-warning}"
  notice:
    backgroundColor: "{colors.field}"
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
---

## Overview

키네틱은 한국어를 사용하는 전기차 운전자가 충전 조건을 입력하고 비용이 낮은 시간대를 판단하는 웹앱이다. 방향은 **차분한·명확한·실용적인 product minimalism**이다. 기존 PDF 유래의 라임·따뜻한 중립색과 Pretendard를 유지하고, 메인색(primary/ring)만 사용자가 승인한 딥 네이비 `#243A5E`를 쓴다. 크림 배경은 새로 도입한 취향이 아니라 기존 브랜드 자산이다. 디스플레이 세리프, 승인된 네이비 외의 새로운 블루, 다크 테마를 도입하지 않는다.

사용자 승인 범위: 기존 라임·Pretendard 유지, 공통 디자인 기준 문서화 후 전체 화면 여백·타이포·컴포넌트 리디자인. **Reskin**으로 제한한다. 이후 사용자가 기존 forest 초록(`#0C5949`) 메인색을 딥 네이비 `#243A5E`로 바꾸도록 직접 선택·승인했다(primary/ring만 변경; 라임, 중립색, 부하 구간·상태 의미색, Pretendard는 그대로). 기능, 라우트, 섹션 순서, API, 입력 이름, URL query, 인증 동작, 계산, 메타데이터 및 실제 콘텐츠는 유지한다. 별도 승인 없이 새 의존성·유료 서비스·커밋·푸시·병합·배포를 하지 않는다.

## Signature Element

모든 화면에서 동일하게 쓰는 **짧은 활성 내비게이션 표시**를 시그니처로 삼는다. 데스크톱 상단과 모바일 하단의 현재 위치는 브랜드(네이비) 텍스트와 선/표시의 조합으로 읽히며 `aria-current="page"`를 유지한다. 홈에 장식적 충전기 일러스트, 가짜 앱 스크린샷, 애니메이션을 추가하지 않는다.

## Colors

YAML은 현재 `src/app/globals.css` 및 기존 설계 문서의 색상을 보존한다. 기존 CSS 명명(`brand`, `ink`, `ink-2`, `ok-bg` 등)은 유지해 기존 사용처가 깨지지 않게 한다. 전경/배경은 쌍으로 적용한다. 실제 텍스트에는 AA 대비가 확보되는 `ink`, `ink-2`를 우선한다. 낮은 대비의 `ink-3`는 중요한 도움말·금액·오류·본문에 사용하지 않는다.

한 화면의 강조는 주 CTA와 활성 내비게이션, 핵심 절감액을 합해 약 3–5곳으로 제한한다. 라임은 절감액 또는 기존 할인 표시에서만 쓴다. 상태색과 시간대 색은 의미를 전달하므로 브랜드 강조 예산과 구분한다. 차트 구간 색상(경부하 초록 `band-light` 포함)과 충전소 가용 상태 초록, 상태 배지 `ok`는 의미색이라 메인색 변경과 무관하게 유지한다. 지도의 '찾는 기준점'은 `--color-brand` 토큰 값을 읽어 쓴다. 차트 구간 색상과 0점 기준 막대 비례는 변경하지 않는다. 구간 색을 무의미한 단색 선차트로 바꾸지 않는다.

## Typography

기존 패키지의 Pretendard Variable을 로컬로 사용한다. 새 외부 폰트 요청 없음. 기본 본문 16px/1.65, 설명·필드 라벨·각주 최소 14px/1.6. 모바일 내비게이션의 짧은 레이블만 12px까지 허용한다. 차트 축의 숫자 라벨은 별도 작은 크기를 유지할 수 있으나 접근 가능한 동일 데이터 표를 보존한다.

페이지 제목은 모바일 28px, 데스크톱 32–36px. 홈 제목은 모바일 36–40px, 데스크톱 최대 56px, 기존 두 줄 의미 유지. 소제목 18–20px. 제목은 자간 -0.02em~-0.035em, 한국어 본문에는 과도한 음수 자간을 적용하지 않는다. `word-break: keep-all`과 안전한 긴 문자열 줄바꿈을 함께 고려한다. 고정폭 수치와 `tabular-nums`는 시각·금액·kWh에 유지한다. 내용 잘림으로 수치·단위·상태를 잃지 않게 한다.

## Layout

4px 기반 간격. 페이지 가로폭은 기존 최대 1280px. 모바일 가로 여백 20px, 태블릿 24px, 데스크톱 32px. 모바일 본문 시작 24px, 데스크톱 시작 40px 내외. 큰 섹션 간 32–64px, 관련 필드/행 간 12–24px로 그룹이 읽히게 한다.

기존 모바일 하단 탭과 데스크톱 상단 내비 전환점 `lg`(1024px)를 보존한다. 하단 safe-area를 고려하며 탭바에 마지막 콘텐츠가 가리지 않도록 본문 여백을 둔다. 페이지가 스크롤의 소유자이며 좁은 화면에 새로운 중첩 스크롤을 추가하지 않는다. 지도는 기존처럼 한 번만 마운트한다. 인증 화면은 적정한 폼 폭, 추천·단가·충전소는 기존 화면별 컬럼 구성을 보존한다. 양쪽 컬럼의 시작점과 제목/설명/컨트롤 정렬을 맞춘다.

홈은 모바일 브랜드 → 설명/CTA → 명시된 추천 예시 → 바로가기 → 출처, 데스크톱은 상단 내비 → 기존 split hero → 기존 특징 그룹 → 출처 순서를 보존한다. 특징 그룹은 동등한 카드 박스의 반복보다 여백과 구분선으로 읽히게 할 수 있으나 내용과 순서를 바꾸지 않는다. 예시 시간·금액은 API 실데이터인 것처럼 꾸미지 않는다.

### Route and state verification matrix

아래 12개 라우트를 각각 375×900, 768×900, 1440×900에서 확인한다.

| Routes | Main states / interactions |
| --- | --- |
| `/` | 두 CTA, 모바일 바로가기, 명확한 예시·출처 |
| `/recommend` | 초기 폼, 모드 전환, 입력/검증, 추천으로 이동 |
| `/recommend/result` | 쿼리 없음, 유효한 추천 결과, 로딩/오류, 조건 수정, 저장 인증 경계 |
| `/timeline` | 날짜 선택, 결과/로딩/오류, 범례·툴팁·할인·고지 |
| `/ask` | 입력, 예시 질문, 준비 중/실패/제한 상태, 추천 이동 |
| `/stations` | 위치 권한/미설정, 필터, 목록/로딩/빈 상태/오류, 지도·목록 전환 |
| `/login`, `/signup` | 폼, 비밀번호 표시, 검증, 게스트 이동 |
| `/me`, `/me/vehicles`, `/me/plans`, `/me/favorites` | 게스트 진입, 인증 후 로딩/빈 상태/오류/목록, 기존 관리 동작 |

실제 계정 생성·데이터 삭제는 수행하지 않는다. 인증 후 상태가 실제로 관찰되지 않았다면 컴포넌트 테스트에서 검증한 범위와 별개로 미검증을 보고한다. 브라우저 fixture는 사용할 경우 실제 서버 결과와 혼동하지 않게 명시한다.

## Elevation & Depth

기본 콘텐츠는 평면 구조와 1px 기존 line 색 구분을 사용한다. 얕은 2단 그림자는 탐색 셸·선택된 주요 결과·오버레이처럼 떠 있는 면에만 사용한다. 모든 카드에 동일한 그림자를 붙이지 않는다. 그라디언트, blur/glass, 장식적 패턴을 추가하지 않는다. 그림자에는 기존 ink의 알파만 사용한다.

## Shapes

기본 `--radius: 12px`에서 작은 8px, 입력/버튼 12px, 카드 20px로 파생한다. pill 999px는 상태 배지 또는 실제 세그먼트처럼 의미 있는 곳에 한정한다. 기존 `rounded-card`, `rounded-field`, `rounded-pill` 사용처와 호환되게 한다. 모든 요소를 동일한 pill로 만들지 않는다.

## Components

공통 Button/ButtonLink, Card, Badge, Field/SelectField, SegmentedControl, Notice 및 내비게이션을 먼저 정리한다. 컴포넌트 API와 기존 이벤트/disabled 속성 전달을 보존한다. 페이지별 직접 입력에도 같은 토큰·상태를 적용한다. 임의의 CSS selector로 전체 DOM을 덮어씌우는 테마보다 공통 primitive와 명확한 클래스 구성을 사용한다.

- **버튼/입력:** 기본 높이 48px, 터치 영역 최소 44px. 주 버튼은 브랜드 네이비, 보조는 흰색·테두리 또는 ghost. 한 화면 한 의사결정에 한 주 CTA. hover는 기존 팔레트의 명도/투명도 변화, focus-visible은 2px ring + offset, active는 색상 변화, disabled는 opacity와 cursor로 구분한다. 로딩은 중복 제출을 막고 상태를 텍스트로 유지한다.
- **폼:** label/input 연결, 도움말/오류 연결, 숫자 단위와 양끝 정렬. 필드 그룹별 여백, 오류 텍스트 및 기존 메시지 유지. 버튼 재배치로 제출을 없애지 않는다.
- **카드/결과:** 주 결과의 숫자와 기간 우선. 기존 비교 및 잠정치/가정/할인 고지는 보존하고 대비를 확보한다. 모든 섹션을 카드 안에 넣지 않는다.
- **차트:** 실제 수치 비례, 구간·축·단위·선택 상태·범례·키보드 툴팁과 숨은 표를 보존한다. 막대의 색 의미를 바꾸지 않는다.
- **내비:** 활성 상태는 색+형태, hover·focus-visible·active 제공. 회원가입 CTA는 홈의 추천 CTA보다 시각적 무게를 낮춘다. 모바일 탭은 각 44px 이상, safe-area 지원.
- **Notice/empty/error:** 오류를 정상 성공처럼 보이게 하지 않는다. 로딩은 기존 구조의 높이를 유지한다. 빈 목록의 안내/CTA, 실패 후 재시도, 401/501/unreachable 구분을 유지한다. 기존 문자열·날짜·수치는 임의로 바꾸지 않는다.

## Motion & Interaction

낮은 모션 강도 2. hover/focus/active에 color, background-color, border-color, opacity만 120–160ms. `transition: all`, bounce, 스크롤 애니메이션, 새 애니메이션 라이브러리 없음. 기존 `prefers-reduced-motion: reduce`를 유지하며 전환을 사실상 즉시 처리한다. 숫자 입력·토글·차트 hover는 반응성 우선.

## Implementation Tokens

`src/app/globals.css`의 `@theme`가 위 계약을 Tailwind 유틸리티로 노출한다. 기존 색 토큰은 그대로이며 아래만 추가·조정했다.

- 타이포: `text-title`(28/1.3) · `text-title-lg`(32/1.3) · `text-section`(20/1.4) · `text-display`(36/1.2) · `text-display-lg`(56/1.15). 페이지 제목은 `text-title lg:text-title-lg`.
- 반경: `rounded-card` 20px · `rounded-field` 12px · `rounded-lg` 8px. 버튼은 `rounded-field`(알약 아님).
- 그림자: `shadow-raised`(선택된 세그먼트), `shadow-float`(차트 툴팁)만. 둘 다 ink 알파.
- 본문 16px/1.65, `word-break: keep-all`, 키보드 초점은 `:where()` 전역 2px 링(컴포넌트가 따로 정하면 그쪽이 우선).
- 버튼 높이: `md` 44px(터치 최소), `lg` 48px(필드와 동일).
- 활성 내비: 상단은 글자 아래 `after:` 선, 하단 탭은 글자 위 `before:` 선, 마이페이지 사이드바는 왼쪽 선 — 모두 `text-brand` + `aria-current="page"`.
- 결과 조건 칩·미확인 알약은 의미 있는 정보라 14px(`text-sm`). 12px는 모바일 내비 레이블과 차트 축·툴팁만.
- 폼 안 보조 링크(차량 관리/로그인)도 클릭 영역 44px(`min-h-11 min-w-11`). 라벨 줄을 `[&>label]:min-h-11`로 같이 키워 select와 겹치지 않게 한다.
- 소형 `select`처럼 `outline-none`을 쓰는 컨트롤은 `focus-visible:outline-2 outline-offset-2 outline-brand`를 직접 준다(전역 링은 a/button 등에만 적용).
- 비활성 Button은 `disabled:cursor-not-allowed`가 보이도록 `pointer-events-none`을 쓰지 않는다. hover/active 색은 `not-disabled:`로 한정하고 클릭 차단은 네이티브 `disabled`가 맡는다.
- 위 클래스 검사는 회귀 방지용이며 실제 높이·겹침·커서·초점 표시는 브라우저 측정으로 확인한다.
- 메인색 `--color-brand`는 `#243a5e`(딥 네이비). 아이콘(`scripts/generate-pwa-icons.mjs`)은 이 값을 읽어 재생성하며 manifest의 배경 `#F1F0EB`는 그대로다.
- `src/design-guard.test.ts`가 transition-all·backdrop-blur·ink-3 텍스트·기존 팔레트 hex 보존을 소스에서 확인한다.

## Do's and Don'ts

- 기존 브랜드·문구·링크·CTA·라우트·섹션 순서·비즈니스 동작을 유지한다.
- 같은 의미의 제목·라벨·여백·입력 높이·보조 텍스트를 전 화면에서 맞춘다.
- 흰/중립 면 위에서 브랜드 네이비와 라임을 제한적으로 사용한다.
- 실제 없는 통계, 예시를 숨긴 실적, 장식적 영어 라벨·번호·아이콘·신규 기능을 만들지 않는다.
- 공통 스타일 정리만 하고 API/요금 계산/인증/시간대 로직·서비스 워커 동작은 바꾸지 않는다.
- 기존 테스트를 스타일 변화에 맞게 삭제하거나 약화하지 않는다. 새 외부 의존성은 승인 없이 추가하지 않는다.

## Accessibility Constraints & Accepted Debt

키보드 탭 순서, visible focus, 의미 있는 heading, label, aria-current, status/alert, disabled 및 오류 처리, 지도 단일 마운트를 보존한다. 스킵 링크를 추가할 경우 기존 주요 콘텐츠에 연결한다. 수평 넘침이 없는 375px 화면과 200% 확대를 확인한다. 차트의 기존 일부 색은 비텍스트 대비가 부족하므로 기존 범례·텍스트·숨은 데이터 표로 보완하고 색을 바꾸지 않는 제약을 유지한다.

**검증 기준:** 기존 baseline은 `npm test` 38파일/542테스트 통과, `npm run lint`, `npm run typecheck` 모두 exit 0. 변경 후 같은 검사 및 `npm run build` 성공, 대표 상호작용 실동작, 최종 변경 파일 SHA256 manifest에 대한 `code-reviewer` 독립 승인 필수. 커밋/푸시/배포하지 않는다.

**성능 예산:** 공개 good 기준인 CLS <0.1을 참고하되 이번 로컬 디자인 비교는 375×900 Chromium, localhost, 미스로틀 데스크톱 CPU/네트워크, 비인증 cold navigation의 `/` 한 표본을 baseline/after로 기록한다. 개발 모드는 컴파일 영향을 받으므로 실제 field/p75 또는 production Lighthouse 통과를 주장하지 않는다. baseline은 컴포넌트 변경 전에 캡처 담당자가 기록한다. 로딩 시 필드·내비·차트 높이를 불필요하게 바꾸지 않고, 새 폰트/이미지/클라이언트 라이브러리를 추가하지 않는다.

**도구 제한:** ui-craft-detect 및 @google/design.md CLI는 현재 프로젝트 의존성에 없어 미실행이다. 승인 없는 신규 패키지 설치로 채우지 않는다. 검사 부재를 0건/통과로 보고하지 않는다. 문서의 YAML/참조와 색상쌍은 이미 설치된 도구 또는 표준 라이브러리로 보조 검사할 수 있으나 공식 lint와 구분한다.

## Research Log

- 기존 소스: `src/app/globals.css`, `src/app/page.tsx`, `src/components/shell/AppShell.tsx`, `package.json`, 기존 프론트엔드 설계 문서. 사용자 승인으로 기존 identity 전체 보존. 메인색은 이후 사용자가 딥 네이비 #243A5E로 변경 승인(라임·의미색·기능 보존).
- 로컬 참조: `omh design data --kind palette|font|ux --context mobile`. Pretendard Korean-first, 본문 14px 하한, 44px hit target, 한 주 CTA 원칙 채택. Pocket Mint 팔레트는 기존 브랜드와 달라 채택하지 않음.
- 변경 전 실행: 38파일/542테스트 및 lint/typecheck 통과. permit 작업공간 개발 서버는 :3001. :3000은 다른 worktree이므로 본 작업 검증으로 쓰지 않음.
- 기존 실제 화면 1280px에서 상단·hero 캡처 관찰. 반복 카드, 작은 도움말, pill 위주 컨트롤, 넓게 분산된 정보가 리디자인 대상. 전체 페이지의 구현 전 baseline/후속 QA 캡처는 별도 artifact에 보관.

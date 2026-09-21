"use client";

import { useSyncExternalStore } from "react";

/**
 * hydration이 끝났는가.
 *
 * '이번 달'을 서버에서 정하면 안 되기 때문에 있다. 서버는 대개 UTC 컨테이너에서 돌고
 * 사용자는 KST다 — 9월 30일 밤 11시에 서버는 "2026-09", 브라우저는 "2026-10"을 그린다.
 * 그게 hydration 불일치다. 그래서 브라우저에 붙은 다음에만 이번 달을 계산한다.
 *
 * useState + useEffect로도 되지만, useSyncExternalStore는 서버 스냅샷을 따로 받아
 * 첫 렌더를 서버와 같게 맞춰 주는 것이 계약이라 실수할 여지가 없다.
 *
 * timeline/hooks.ts에 같은 훅이 있다. 불러 쓰지 않고 복제한 이유는 그 모듈이
 * 하루 단가 화면의 것이고(matchMedia 훅과 한 파일), 충전 기록 화면이 다른 기능의
 * 내부 모듈에 의존하게 만들고 싶지 않아서다. 열두 줄짜리 훅이라 복제가 더 싸다.
 */
const NEVER_CHANGES = () => () => {};

export function useIsHydrated(): boolean {
  return useSyncExternalStore(
    NEVER_CHANGES,
    () => true,
    () => false,
  );
}

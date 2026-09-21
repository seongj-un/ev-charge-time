"use client";

import { useSyncExternalStore } from "react";

/**
 * 이 화면이 쓰는 훅 둘. 서로 다른 일을 하지만 같은 장치로 푼다 — useSyncExternalStore.
 *
 * 둘 다 "서버에서는 알 수 없고 브라우저에서만 알 수 있는 것"을 읽는다. 그런 값을
 * useState + useEffect로 넣으면 서버 HTML과 첫 클라이언트 렌더가 어긋날 위험을
 * 개발자가 매번 손으로 지켜야 한다. useSyncExternalStore는 서버 스냅샷을 따로 받아서
 * 첫 렌더를 서버와 같게 맞춰 주고, hydration이 끝난 다음에 실제 값으로 한 번 더 그린다.
 */

/** 구독할 게 없는 훅용. (hydration 여부는 바뀌는 순간이 한 번뿐이다) */
const NEVER_CHANGES = () => () => {};

/**
 * hydration이 끝났는가.
 *
 * '오늘'을 서버에서 정하면 안 되기 때문에 있다. 서버는 대개 UTC 컨테이너에서 돌고
 * 사용자는 KST다 — 자정 근처에는 서버가 "10월 9일", 브라우저가 "10월 10일"을 그린다.
 * 이게 hydration 불일치다. 그래서 브라우저에 붙은 뒤에만 오늘을 계산한다.
 */
export function useIsHydrated(): boolean {
  return useSyncExternalStore(
    NEVER_CHANGES,
    () => true,
    () => false,
  );
}

const DESKTOP_QUERY = "(min-width: 1024px)"; /* Tailwind lg */

function mediaQuery(): MediaQueryList | null {
  // jsdom에는 matchMedia가 없다. 이 훅 때문에 테스트가 죽으면 안 된다.
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
  return window.matchMedia(DESKTOP_QUERY);
}

function subscribeToDesktop(onChange: () => void): () => void {
  const query = mediaQuery();
  if (!query) return () => {};
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getDesktopSnapshot(): boolean {
  return mediaQuery()?.matches ?? false;
}

function getDesktopServerSnapshot(): boolean {
  return false; /* 모바일 우선 */
}

/**
 * 지금 화면이 데스크톱 폭인가.
 *
 * CSS로 못 푸는 것 하나 때문에 있다: 차트의 x축 눈금 간격(labelEvery)과 막대 높이는
 * 숫자 prop이라 미디어 쿼리로 바꿀 수 없다. 모바일에서 24개 시각을 다 찍으면
 * 글자가 서로 겹쳐 아무것도 읽을 수 없다.
 */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribeToDesktop,
    getDesktopSnapshot,
    getDesktopServerSnapshot,
  );
}

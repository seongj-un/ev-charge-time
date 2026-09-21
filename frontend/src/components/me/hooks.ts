"use client";

import { useSyncExternalStore } from "react";

/**
 * hydration이 끝났는가.
 *
 * '이번 달'을 서버에서 정하면 안 되기 때문에 있다. 서버는 대개 UTC 컨테이너에서 돌고
 * 사용자는 KST다 — 말일 자정 근처에는 서버가 "2026-09", 브라우저가 "2026-10"을 그린다.
 * 그게 hydration 불일치다. useSyncExternalStore는 서버 스냅샷(false)을 따로 받아
 * 첫 렌더를 서버와 글자 하나까지 같게 맞추고, 붙은 뒤에 한 번 더 그린다.
 * useEffect + setState로는 같은 보장을 얻을 수 없고, Next 16의
 * react-hooks/set-state-in-effect 규칙에도 걸린다.
 *
 * 같은 훅이 src/components/timeline/hooks.ts에도 있다. 불러 쓰지 않고 베낀 이유는
 * 지금 타임라인 화면을 다른 작업자가 동시에 고치고 있어서다 — 그쪽이 파일을 옮기면
 * 이 화면이 같이 깨진다. 여덟 줄짜리 훅이라 옮겨 적는 값이 더 싸다.
 */
const NEVER_CHANGES = () => () => {};

export function useIsHydrated(): boolean {
  return useSyncExternalStore(
    NEVER_CHANGES,
    () => true,
    () => false,
  );
}

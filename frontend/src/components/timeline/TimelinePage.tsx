"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { TimelineScreen } from "./TimelineScreen";
import { isDay, isMode } from "./timeline-view";

/**
 * 하루 단가 화면의 주소 담당.
 *
 * 날짜와 충전 방식을 컴포넌트 state에만 두면 새로고침하면 오늘로 돌아가고,
 * "10월 10일 이렇게 나오는데 봐 줘"라고 링크를 보낼 수가 없다. 그래서 URL이 정본이다.
 *
 * replace를 쓰는 이유: ◀▶로 날짜를 넘길 때마다 히스토리가 쌓이면 뒤로 가기를
 * 스무 번 눌러야 이 화면을 벗어난다. 날짜 이동은 새 페이지가 아니라 같은 화면의 상태다.
 */
export function TimelinePage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const dayParam = searchParams.get("day");
  const modeParam = searchParams.get("mode");
  // 글자 그대로 넘긴다. 알아볼 수 있는 값인지는 칸을 들고 있는 TimelineScreen이 가린다.
  const priceParam = searchParams.get("public_base_price");

  // 주소창은 누구나 고친다. 못 알아보는 값은 무시하고 기본값으로 간다.
  const day = isDay(dayParam) ? dayParam : null;
  const mode = isMode(modeParam) ? modeParam : "self_low";

  const handleQueryChange = useCallback(
    (query: { day: string; mode: string; publicBasePrice?: number }) => {
      const next = new URLSearchParams();
      next.set("day", query.day);
      next.set("mode", query.mode);
      // 공용 급속 단가도 남긴다. 새로고침할 때마다 충전기 요금을 다시 치게 하지 않는다.
      if (query.publicBasePrice !== undefined) {
        next.set("public_base_price", String(query.publicBasePrice));
      }
      // 차트를 보고 있는데 날짜를 넘길 때마다 맨 위로 튀면 안 된다.
      router.replace(`/timeline?${next.toString()}`, { scroll: false });
    },
    [router],
  );

  return (
    <TimelineScreen
      initialDay={day}
      initialMode={mode}
      initialPublicBasePrice={priceParam}
      onQueryChange={handleQueryChange}
    />
  );
}

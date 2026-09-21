import type { Metadata } from "next";
import { Suspense } from "react";

import { TimelinePage } from "@/components/timeline/TimelinePage";
import { TimelineScreen } from "@/components/timeline/TimelineScreen";

export const metadata: Metadata = {
  title: "하루 단가",
  description:
    "하루 24시간의 전기요금 단가를 시간대별로 봅니다. 날짜를 바꿔 계절·요일에 따라 요금이 어떻게 달라지는지 확인할 수 있습니다.",
};

/**
 * /timeline — F-05·F-06.
 *
 * TimelinePage가 useSearchParams로 ?day=·?mode=를 읽는다. 그 훅은 프리렌더 때
 * 가장 가까운 Suspense 경계까지를 클라이언트 렌더로 돌린다. 경계를 여기 두면
 * 셸(상단 내비·탭바)은 정적으로 나가고 이 화면만 브라우저에서 채워진다.
 *
 * fallback으로 같은 화면을 날짜 없이 그린다. 따로 만든 스켈레톤을 쓰면 실제 화면과
 * 어긋나 로딩이 끝날 때 레이아웃이 튄다.
 */
export default function Page() {
  return (
    <Suspense fallback={<TimelineScreen />}>
      <TimelinePage />
    </Suspense>
  );
}

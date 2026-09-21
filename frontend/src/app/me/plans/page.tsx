import type { Metadata } from "next";
import { Suspense } from "react";

import { PlansScreen } from "@/components/plans/PlansScreen";
import { PageContainer } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "충전 기록",
  description:
    "저장한 충전 계획을 달별로 모아 봅니다. 그달에 저장한 건수와 예상 절감 합계를 함께 보여줍니다.",
};

/**
 * /me/plans — F-13.
 *
 * PlansScreen이 useSearchParams로 ?month=를 읽는다. 그 훅은 프리렌더 때 가장 가까운
 * Suspense 경계까지를 클라이언트 렌더로 돌리므로, 경계를 여기 두어 셸(상단 내비·탭바)은
 * 정적으로 나가게 한다. 하루 단가 화면(/timeline)과 같은 구조다.
 */
export default function Page() {
  return (
    <Suspense fallback={<PlansFallback />}>
      <PlansScreen />
    </Suspense>
  );
}

/** 제목 자리를 미리 잡아 둔다 — 내용이 들어올 때 화면이 튀지 않는다. */
function PlansFallback() {
  return (
    <PageContainer className="pb-10">
      <h1 className="text-xl font-bold lg:text-[26px]">충전 기록</h1>
      <p role="status" className="mt-6 text-sm text-ink-3">
        충전 기록을 불러오고 있어요…
      </p>
    </PageContainer>
  );
}

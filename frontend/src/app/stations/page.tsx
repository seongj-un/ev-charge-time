import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/AppShell";
import { PinIcon } from "@/components/shell/icons";
import { ComingSoon } from "@/components/ui/ComingSoon";

export const metadata: Metadata = {
  title: "주변 충전소",
};

export default function StationsPage() {
  return (
    <PageContainer>
      <ComingSoon
        title="주변 충전소"
        reason="한국환경공단 전기차 충전소 정보 API를 연동한 뒤 열립니다. 아직 받아 온 충전기 상태가 없어서 목록을 비워 뒀어요."
      >
        {/* 지도 자리만 남긴다 — 크기와 위치를 미리 잡아 두면 연동 때 레이아웃이 안 흔들린다 */}
        <div className="flex h-56 flex-col items-center justify-center gap-2 rounded-card border border-dashed border-line bg-sunken text-ink-3 lg:h-72">
          <PinIcon className="size-6" />
          <span className="text-sm font-bold">지도 영역</span>
        </div>
      </ComingSoon>
    </PageContainer>
  );
}

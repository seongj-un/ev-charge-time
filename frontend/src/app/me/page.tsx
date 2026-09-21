import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/AppShell";
import { ComingSoon } from "@/components/ui/ComingSoon";

export const metadata: Metadata = {
  title: "내 정보",
};

export default function MePage() {
  return (
    <PageContainer>
      <ComingSoon
        title="내 정보"
        reason="회원 인증 API를 연동한 뒤 열립니다. 기본 차량과 저장한 추천, 즐겨찾는 충전소는 로그인이 붙어야 보여드릴 수 있어요."
      />
    </PageContainer>
  );
}

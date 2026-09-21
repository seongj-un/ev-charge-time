import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/AppShell";
import { ComingSoon } from "@/components/ui/ComingSoon";

export const metadata: Metadata = {
  title: "회원가입",
};

export default function SignupPage() {
  return (
    <PageContainer>
      <ComingSoon
        title="회원가입"
        reason="회원 인증 API를 연동한 뒤 열립니다. 가입은 추천 결과를 저장할 때만 필요하고, 추천 자체는 지금도 바로 받을 수 있어요."
      />
    </PageContainer>
  );
}

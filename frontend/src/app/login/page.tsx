import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/AppShell";
import { ComingSoon } from "@/components/ui/ComingSoon";

export const metadata: Metadata = {
  title: "로그인",
};

export default function LoginPage() {
  return (
    <PageContainer>
      <ComingSoon
        title="로그인"
        reason="회원 인증 API를 연동한 뒤 열립니다. 추천은 로그인 없이도 전부 쓸 수 있으니 그대로 이용하세요."
      />
    </PageContainer>
  );
}

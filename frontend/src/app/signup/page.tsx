import type { Metadata } from "next";

import { SignupForm } from "@/components/auth/SignupForm";
import { PageContainer } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "회원가입",
  description:
    "이메일과 비밀번호만으로 가입합니다. 추천 결과 저장과 내 차량 등록에 쓰입니다.",
};

/**
 * /signup — F-11.
 *
 * 가입은 201과 함께 세션 쿠키를 돌려준다. 가입한 사람을 로그인 화면으로
 * 되돌리지 않고 곧장 마이페이지로 보내는 이유다 (SignupForm 참고).
 */
export default function SignupPage() {
  return (
    <PageContainer>
      <SignupForm />
    </PageContainer>
  );
}

import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";
import { PageContainer } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "로그인",
  description: "추천 결과를 저장하고 내 차량을 불러오려면 로그인하세요.",
};

/**
 * /login — F-11.
 *
 * "돌아갈 곳"을 서버에서 읽어 폼에 넘긴다. useSearchParams로 읽으면 Suspense 경계가
 * 필요하고 테스트마다 라우터를 흉내 내야 하는데, 이 화면이 쿼리에서 쓰는 건 next 하나뿐이다.
 * (추천 결과의 "로그인하고 저장"이 ?next=로 결과 주소를 실어 보낸다.)
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const next = Array.isArray(params.next) ? params.next[0] : params.next;

  return (
    <PageContainer>
      <LoginForm nextPath={internalPath(next)} />
    </PageContainer>
  );
}

/**
 * ?next=는 주소창에서 누구나 고친다. 받은 값을 그대로 router.push에 넘기면
 * "로그인 링크를 눌렀더니 남의 사이트"가 되는 열린 리다이렉트가 된다.
 * 앱 안의 절대 경로만 통과시킨다 — `//evil.com`은 슬래시로 시작하지만
 * 프로토콜 상대 URL이라 외부 주소다.
 */
function internalPath(next: string | undefined): string | null {
  if (!next || !next.startsWith("/")) return null;
  if (next.startsWith("//") || next.startsWith("/\\")) return null;
  return next;
}

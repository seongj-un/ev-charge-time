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
 *
 * 문자열 앞부분만 보면 안 된다. URL 파서는 탭·줄바꿈을 지우고 `\`를 `/`로
 * 읽어서, `/\t/evil.com`(?next=%2F%09%2Fevil.com)은 앞부분 검사를 통과한 뒤
 * `//evil.com`이 된다. 그래서 제어문자·역슬래시는 아예 거절하고, 실제로 파싱한
 * 결과의 origin이 우리 쪽인지 본다. 넘기는 것도 파싱한(정규화된) 경로다.
 */
const INTERNAL = "http://internal.invalid";

function internalPath(next: string | undefined): string | null {
  if (!next || !next.startsWith("/")) return null;
  // 제어문자(U+0000–U+001F, U+007F)와 역슬래시는 정상 경로에 나올 일이 없다.
  if (/[\u0000-\u001f\u007f\\]/.test(next)) return null;
  let url: URL;
  try {
    url = new URL(next, INTERNAL);
  } catch {
    return null;
  }
  if (url.origin !== INTERNAL) return null;
  return `${url.pathname}${url.search}${url.hash}`;
}

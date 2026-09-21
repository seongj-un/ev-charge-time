import type { Metadata } from "next";

import { ResultView } from "@/components/result/ResultView";

export const metadata: Metadata = {
  title: "추천 결과",
  description: "입력한 조건으로 가장 싸게 충전할 수 있는 시간과 그때의 예상 요금입니다.",
};

/**
 * 조건은 URL 쿼리에 실려 온다 (/recommend에서 넘겨준다).
 *
 * 서버에서 `searchParams`를 받아 쿼리 문자열로 만들어 넘기는 이유:
 * 이 화면은 추천·단가를 브라우저에서 부르므로 어차피 클라이언트 컴포넌트가 필요한데,
 * 서버가 쿼리를 읽어 주면 useSearchParams와 그에 딸린 Suspense 경계가 필요 없다.
 * 화면이 쿼리 문자열 하나만 받으니 테스트에서도 라우터를 흉내 낼 일이 없다.
 *
 * searchParams를 읽는 순간 이 라우트는 요청 시점 렌더가 된다 — 조건마다 결과가
 * 다른 화면이라 미리 만들어 둘 것이 애초에 없다.
 */
export default async function RecommendResultPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return <ResultView query={toQueryString(await searchParams)} />;
}

/** 같은 키가 여러 번 들어오면 첫 값만 쓴다 — 조건은 하나씩만 의미가 있다. */
function toQueryString(params: Record<string, string | string[] | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const first = Array.isArray(value) ? value[0] : value;
    if (first !== undefined) query.set(key, first);
  }
  return query.toString();
}

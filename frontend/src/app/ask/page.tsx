import type { Metadata } from "next";

import { AskScreen } from "@/components/ask/AskScreen";

export const metadata: Metadata = {
  title: "질문으로 충전 시간 찾기",
  description:
    "말하듯 물어보면 조건을 읽어 가장 싼 충전 시간을 찾아 줍니다. 금액과 시각은 서버가 계산한 값입니다.",
};

/**
 * /ask — F-10 자연어 질의.
 *
 * 다른 화면과 달리 Suspense 경계가 없다. 이 화면은 useSearchParams를 쓰지 않는다 —
 * 대화는 URL에 싣지 않는다. 질문에 배터리 용량이나 생활 습관이 섞여 들어가는데,
 * 그게 주소창과 방문 기록에 남으면 링크 하나로 새어 나간다.
 */
export default function Page() {
  return <AskScreen />;
}

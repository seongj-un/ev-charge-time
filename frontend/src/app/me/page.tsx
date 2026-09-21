import type { Metadata } from "next";

import { MeSummary } from "@/components/me/MeSummary";

export const metadata: Metadata = {
  title: "내 정보",
  description:
    "기본 차량과 이번 달 저장한 충전 계획, 계정 설정을 한 화면에서 봅니다.",
};

/**
 * /me — 마이페이지 요약 (F-11·F-12·F-13).
 *
 * 화면 본체가 클라이언트 컴포넌트인 이유: 로그인 여부를 httpOnly 쿠키로만 알 수 있어
 * GET /api/me의 응답을 보고 판단해야 하고, 그 판단은 SessionProvider가 브라우저에서 한다.
 * 이 파일은 metadata를 내보내려고 서버 컴포넌트로 남겨 둔다.
 */
export default function MePage() {
  return <MeSummary />;
}

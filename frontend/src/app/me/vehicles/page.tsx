import type { Metadata } from "next";

import { VehiclesScreen } from "@/components/me/VehiclesScreen";

export const metadata: Metadata = {
  title: "내 차량",
  description:
    "자주 쓰는 차량의 배터리 용량과 충전기 출력을 저장해 두고, 기본 차량을 고릅니다.",
};

/** /me/vehicles — F-12. 목록·추가·수정·삭제가 한 화면에서 끝난다. */
export default function VehiclesPage() {
  return <VehiclesScreen />;
}

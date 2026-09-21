import type { Metadata } from "next";

import { StationsScreen } from "@/components/stations/StationsScreen";

export const metadata: Metadata = {
  title: "주변 충전소",
  description: "가까운 충전소와 충전기 사용 가능 여부를 확인하세요.",
};

export default function StationsPage() {
  return <StationsScreen />;
}

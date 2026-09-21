import type { Metadata } from "next";

import { FavoritesScreen } from "@/components/stations/FavoritesScreen";

export const metadata: Metadata = {
  title: "즐겨찾는 충전소",
  description: "자주 쓰는 충전소를 모아 두고 상태를 바로 확인하세요.",
};

export default function FavoritesPage() {
  return <FavoritesScreen />;
}

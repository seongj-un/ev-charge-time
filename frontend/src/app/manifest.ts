import type { MetadataRoute } from "next";

import { SERVICE_NAME } from "@/components/shell/nav";

/**
 * layout.tsx가 가리키는 /manifest.webmanifest를 Next가 이 파일로 만들어 준다.
 *
 * public/icons의 실제 PNG를 참조한다. maskable은 중앙 80% 안전 영역을 지킨다.
 * 재생성: frontend에서 node scripts/generate-pwa-icons.mjs 실행.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SERVICE_NAME,
    short_name: SERVICE_NAME,
    description:
      "2026년 계절·시간대별 전기요금 개편을 반영해 가장 싸게 충전할 수 있는 시간을 찾아드립니다.",
    lang: "ko",
    start_url: "/",
    display: "standalone",
    background_color: "#F1F0EB",
    theme_color: "#F1F0EB",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

import type { MetadataRoute } from "next";

import { SERVICE_NAME } from "@/components/shell/nav";

/**
 * layout.tsx가 가리키는 /manifest.webmanifest를 Next가 이 파일로 만들어 준다.
 *
 * icons는 일부러 비워 뒀다. 아직 아이콘 에셋이 없는데 경로만 적어 두면 설치할 때
 * 404가 나고, 브라우저는 그걸 조용히 삼켜서 나중에 원인을 찾기 어렵다.
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
    icons: [],
  };
}

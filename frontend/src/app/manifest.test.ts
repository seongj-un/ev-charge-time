import { describe, expect, test } from "vitest";

import { SERVICE_NAME } from "@/components/shell/nav";

import manifest from "./manifest";

describe("manifest", () => {
  test("서비스 이름과 디자인 배경색으로 설치형 앱을 정의한다", () => {
    const result = manifest();

    expect(result.name).toBe(SERVICE_NAME);
    expect(result.short_name).toBe(SERVICE_NAME);
    expect(result.start_url).toBe("/");
    expect(result.display).toBe("standalone");
    expect(result.background_color).toBe("#F4F6F9");
    expect(result.theme_color).toBe("#F4F6F9");
  });

  test("일반 설치 아이콘과 안전 영역을 갖춘 maskable PNG를 제공한다", () => {
    expect(manifest().icons).toEqual([
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ]);
  });
});

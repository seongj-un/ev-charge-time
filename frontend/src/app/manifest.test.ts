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
    expect(result.background_color).toBe("#F1F0EB");
    expect(result.theme_color).toBe("#F1F0EB");
  });

  /** 아이콘 에셋이 아직 없다 — 없는 파일을 가리키면 설치 시 404가 난다. */
  test("아이콘 에셋이 생기기 전까지 icons는 비워 둔다", () => {
    expect(manifest().icons).toEqual([]);
  });
});

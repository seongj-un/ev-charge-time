import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, sep } from "node:path";

import { describe, expect, test } from "vitest";

/**
 * 디자인 계약(DESIGN.md)의 기계로 확인 가능한 부분을 소스에서 지킨다.
 * 스타일 줄을 하나 바꿀 때마다 같은 실수가 돌아오지 않게 하는 안전망이지,
 * 화면이 예쁜지를 증명하는 테스트는 아니다.
 */
// jsdom 환경에서는 import.meta.url이 file: URL이 아니라서 URL로 위치를 구하지 않는다.
// `npm test`는 frontend 루트(vitest.config.ts가 있는 곳)에서 실행되므로 cwd 기준으로 src를 찾는다.
const SRC = join(process.cwd(), "src") + sep;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const sources = walk(SRC)
  .filter((path) => /\.(tsx|css)$/.test(path) && !/\.test\.tsx?$/.test(path))
  .map((path) => ({ path: path.slice(SRC.length), text: readFileSync(path, "utf8") }));

describe("디자인 계약", () => {
  test("소스를 읽었다", () => {
    expect(sources.length).toBeGreaterThan(30);
  });

  test("transition-all·backdrop-blur·중요도(!) 접두 유틸리티를 쓰지 않는다", () => {
    const hits = sources.flatMap(({ path, text }) => {
      const found: string[] = [];
      if (text.includes("transition-all")) found.push("transition-all");
      if (text.includes("backdrop-blur")) found.push("backdrop-blur");
      // Tailwind의 `!bg-ink` 같은 강제 덮어쓰기. (globals.css의 reduced-motion 규칙은 CSS라 대상이 아니다.)
      if (path.endsWith(".tsx") && /(^|[\s"'`])![a-z][\w:]*-[\w[\]/.%-]+/.test(text)) {
        found.push("important-modifier");
      }
      return found.map((what) => `${path}: ${what}`);
    });
    expect(hits).toEqual([]);
  });

  test("의미 있는 글자에 낮은 대비의 ink-3를 쓰지 않는다 (placeholder·장식 점·비활성만 예외)", () => {
    const hits = sources.flatMap(({ path, text }) =>
      [...text.matchAll(/(?<!placeholder:)(?<!before:)(?<!\]:)text-ink-3/g)].map(() => path),
    );
    expect(hits).toEqual([]);
  });

  test("버튼은 알약이 아니라 12px 필드 반경을 쓴다", () => {
    const button = sources.find((source) => source.path === "components/ui/Button.tsx");
    expect(button?.text).not.toContain("rounded-pill");
    expect(button?.text).toContain("rounded-field");
  });

  test("팔레트 hex가 DESIGN.md 계약대로 있다 (네이비·라임·부하구간·상태색은 이전부터 그대로)", () => {
    const css = sources.find((source) => source.path === "app/globals.css")?.text ?? "";
    const palette = [
      // 2026-11 리디자인: 옅은 회색 중립색 + 블루 메인색 단계
      "#f4f6f9", "#ffffff", "#eceff3", "#f8f9fb", "#e1e5ea",
      "#16171b", "#4e5561", "#8a909a", "#2450d6", "#1c40b0", "#eaf0fd",
      // 바뀌지 않은 라임·의미색
      "#c4de3c",
      "#2f7c5a", "#c88918", "#b7422e", "#e2efe6", "#275742",
      "#f6ead0", "#644303",
    ];
    for (const hex of palette) expect(css).toContain(hex);
    // 크림 중립색은 메인색을 탁하게 만들어 걷어 냈다
    expect(css).not.toMatch(/--color-canvas:\s*#f1f0eb/);
  });

  test("수치용 .tnum은 한글이 없는 고정폭 글꼴로 바꾸지 않는다 (원·시간이 □로 깨진다)", () => {
    const css = sources.find((source) => source.path === "app/globals.css")?.text ?? "";
    const tnum = css.match(/\.tnum\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(tnum).toContain("tabular-nums");
    expect(tnum).not.toContain("--font-mono");
  });

  test("브랜드 토큰은 사용자가 바꾸기로 한 블루 #2450d6이고 DESIGN.md와 일치한다", () => {
    const css = sources.find((source) => source.path === "app/globals.css")?.text ?? "";
    expect(css).toMatch(/--color-brand:\s*#2450d6;/i);
    expect(css).not.toContain("#0c5949");
    const design = readFileSync(join(process.cwd(), "DESIGN.md"), "utf8");
    expect(design).toMatch(/primary:\s*"#2450D6"/);
    expect(design).toMatch(/ring:\s*"#2450D6"/);
  });

  test("지도 '찾는 기준점'은 하드코딩 색이 아니라 브랜드 토큰을 쓴다", () => {
    const map = sources.find((source) => source.path === "components/stations/StationMap.tsx")?.text ?? "";
    expect(map).not.toContain("#0c5949");
    expect(map).toContain("--color-brand");
    // 기준점 마커 블록: 색 두 필드 모두 토큰에서 읽은 값이어야 한다.
    const marker = map.match(/circleMarker\(\[center\.lat, center\.lng\], \{([\s\S]*?)\}\)\.bindPopup\("찾는 기준점"\)/)?.[1] ?? "";
    expect(marker).toMatch(/color:\s*brand,/);
    expect(marker).toMatch(/fillColor:\s*brand,/);
    expect(marker).not.toMatch(/#[\da-f]{3,6}/i);
    // 충전소 가용성 색은 그대로다.
    expect(map).toContain("#2f7c5a");
    expect(map).toContain("#7c7d80");
  });

  test("다크 모드를 넣지 않는다", () => {
    const css = sources.find((source) => source.path === "app/globals.css")?.text ?? "";
    expect(css).toContain("color-scheme: light only");
    expect(css).not.toContain("prefers-color-scheme");
  });
});

describe("터치 영역·글자 크기 하한 (브라우저 QA-01~04 회귀)", () => {
  const read = (path: string) => sources.find((source) => source.path === path)?.text ?? "";

  test("배지는 14px 아래 글자를 쓰지 않는다", () => {
    const badge = read("components/ui/Badge.tsx");
    expect(badge).toContain("text-sm");
    expect(badge).not.toMatch(/text-xs|text-\[1[0-3]px\]/);
  });

  test("지역 select는 높이 48px(min-h-12) 이상이다", () => {
    expect(read("components/stations/StationsScreen.tsx")).toMatch(/<select[\s\S]*?className=\{`[^`]*min-h-12/);
  });

  test("'사용 가능만' 체크박스 라벨은 클릭 영역 44px(min-h-11) 이상이다", () => {
    expect(read("components/stations/StationsScreen.tsx")).toMatch(
      /<label className="[^"]*min-h-11[^"]*">\s*<input\s+type="checkbox"/,
    );
  });

  test("태양광 토글은 데스크톱에서도 44px(lg:min-h-11) 이상이다", () => {
    expect(read("components/timeline/SolarOverlayButton.tsx")).toContain("lg:min-h-11");
  });

  test("결과 조건 칩·미확인 알약은 14px(text-sm) 아래 글자를 쓰지 않는다", () => {
    const header = read("components/result/ResultHeader.tsx");
    expect(header).not.toMatch(/text-xs|text-\[1[0-3]px\]/);
    expect(header.match(/text-sm font-bold/g)?.length).toBeGreaterThanOrEqual(3);
  });

  test("차량 관리/로그인 링크는 24px(min-h-6)가 아니라 44px(min-h-11) 클릭 영역이다", () => {
    const form = read("components/recommend/ChargeForm.tsx");
    expect(form).not.toContain("min-h-6");
    expect(form).toMatch(/href=\{vehicleLinkHref\}\s+className="[^"]*min-h-11/);
    // 링크가 select 위에 겹치지 않도록 라벨 줄도 같은 높이를 확보한다 (SelectField API는 그대로, 호출부 className 훅).
    expect(form).toMatch(/<SelectField[\s\S]*?label="내 차량"[\s\S]*?\[&>label\]:min-h-11/);
    expect(form).toMatch(/<SelectField[\s\S]*?label="내 차량"[\s\S]*?\[&>label\]:mb-0/);
    expect(form).toContain("[&_select]:cursor-not-allowed");
  });

  test("지역 select는 outline-none 대신 2px 초점 윤곽(브랜드색 + offset)을 가진다", () => {
    const stations = read("components/stations/StationsScreen.tsx");
    const select = stations.match(/<select[\s\S]*?className=\{`([^`]*)`/)?.[1] ?? "";
    expect(select).not.toContain("outline-none");
    expect(select).toContain("focus-visible:outline-2");
    expect(select).toContain("focus-visible:outline-offset-2");
    expect(select).toContain("focus-visible:outline-brand");
  });

  test("Button은 pointer-events-none으로 disabled 커서를 죽이지 않는다", () => {
    const button = read("components/ui/Button.tsx");
    expect(button).toContain("disabled:cursor-not-allowed");
    expect(button).not.toContain("pointer-events-none");
  });
});

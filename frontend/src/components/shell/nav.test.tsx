import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { TabBar } from "./TabBar";
import { TopNav } from "./TopNav";

let pathname = "/timeline";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

vi.mock("@/components/auth/SessionProvider", () => ({
  useSession: () => ({ status: "anonymous", user: null }),
}));

/**
 * 상단·하단 내비는 같은 신호(메인색)로 현재 위치를 보여준다:
 * 상단 — aria-current="page" + 메인색 글자 + 아래 메인색 선(::after)
 * 하단 — aria-current="page" + 메인색 글자 + 아이콘 뒤 옅은 메인색 칩
 * 색만이 아니라 모양(선·칩)으로도 구분된다.
 */
const tokens = (element: Element) => element.className.split(/\s+/);
describe("TopNav 활성 표시", () => {
  test("현재 화면만 aria-current와 브랜드 글자·선을 가진다", () => {
    pathname = "/timeline";
    render(<TopNav />);

    const current = screen.getByRole("link", { name: "하루 단가" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(tokens(current)).toContain("text-brand");
    expect(tokens(current)).toContain("after:bg-brand");

    const other = screen.getByRole("link", { name: "주변 충전소" });
    expect(other).not.toHaveAttribute("aria-current");
    expect(tokens(other)).not.toContain("text-brand");
    expect(tokens(other)).toContain("after:bg-transparent");
  });

  test("추천 결과 화면은 추천 탭이 활성이다", () => {
    pathname = "/recommend/result";
    render(<TopNav />);

    expect(screen.getByRole("link", { name: "충전 시간 추천" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "하루 단가" })).not.toHaveAttribute("aria-current");
  });

  test("손님의 회원가입은 보조 버튼이라 테두리만 있고 채운 면을 쓰지 않는다", () => {
    pathname = "/";
    render(<TopNav />);

    const signup = screen.getByRole("link", { name: "회원가입" });
    expect(tokens(signup)).toContain("border-line");
    expect(tokens(signup).filter((token) => /^bg-(ink|brand|accent)$/.test(token))).toEqual([]);
  });
});

describe("TabBar 활성 표시", () => {
  test("현재 화면만 aria-current와 브랜드 글자·선을 가진다", () => {
    pathname = "/stations";
    render(<TabBar />);

    const current = screen.getByRole("link", { name: "충전소" });
    expect(current).toHaveAttribute("aria-current", "page");
    const chip = current.querySelector("span")!;
    expect(tokens(current)).toContain("text-brand");
    expect(tokens(chip)).toContain("bg-brand-soft");

    const home = screen.getByRole("link", { name: "홈" });
    expect(home).not.toHaveAttribute("aria-current");
    expect(tokens(home)).not.toContain("text-brand");
    expect(tokens(home.querySelector("span")!)).not.toContain("bg-brand-soft");
  });

  test("홈은 정확히 / 일 때만 활성이다", () => {
    pathname = "/";
    render(<TabBar />);

    expect(screen.getByRole("link", { name: "홈" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link").filter((link) => link.hasAttribute("aria-current"))).toHaveLength(1);
  });

  test("탭 하나는 44px 이상의 터치 영역(min-h-16)을 가진다", () => {
    pathname = "/";
    render(<TabBar />);

    for (const link of screen.getAllByRole("link")) {
      expect(tokens(link)).toContain("min-h-16");
    }
  });
});

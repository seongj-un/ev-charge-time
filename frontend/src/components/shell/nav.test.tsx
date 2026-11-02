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
 * 상단·하단 내비는 같은 시그니처로 현재 위치를 보여준다:
 * aria-current="page" + 브랜드(네이비) 글자 + 짧은 선(::before/::after 배경이 브랜드색).
 */
describe("TopNav 활성 표시", () => {
  test("현재 화면만 aria-current와 브랜드 글자·선을 가진다", () => {
    pathname = "/timeline";
    render(<TopNav />);

    const current = screen.getByRole("link", { name: "하루 단가" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current.className).toContain("text-brand");
    expect(current.className).toContain("after:bg-brand");

    const other = screen.getByRole("link", { name: "주변 충전소" });
    expect(other).not.toHaveAttribute("aria-current");
    expect(other.className).not.toContain("text-brand");
    expect(other.className).toContain("after:bg-transparent");
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

  test("손님의 회원가입은 보조 버튼이라 어두운 면을 쓰지 않는다", () => {
    pathname = "/";
    render(<TopNav />);

    const signup = screen.getByRole("link", { name: "회원가입" });
    expect(signup.className).toContain("border-line");
    expect(signup.className).not.toContain("bg-ink ");
  });
});

describe("TabBar 활성 표시", () => {
  test("현재 화면만 aria-current와 브랜드 글자·선을 가진다", () => {
    pathname = "/stations";
    render(<TabBar />);

    const current = screen.getByRole("link", { name: "충전소" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current.className).toContain("text-brand");
    expect(current.className).toContain("before:bg-brand");

    const home = screen.getByRole("link", { name: "홈" });
    expect(home).not.toHaveAttribute("aria-current");
    expect(home.className).toContain("before:bg-transparent");
  });

  test("홈은 정확히 / 일 때만 활성이다", () => {
    pathname = "/";
    render(<TabBar />);

    expect(screen.getByRole("link", { name: "홈" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link").filter((link) => link.hasAttribute("aria-current"))).toHaveLength(1);
  });

  test("탭 하나는 44px 이상의 터치 영역(min-h-14)을 가진다", () => {
    pathname = "/";
    render(<TabBar />);

    for (const link of screen.getAllByRole("link")) {
      expect(link.className).toContain("min-h-14");
    }
  });
});

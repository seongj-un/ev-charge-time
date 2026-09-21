import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { okRoutes, stubApi, type ApiCall, type Route } from "@/components/me/test-api";

import MePage, { metadata } from "./page";

/*
 * 화면 동작은 MeSummary.test.tsx가 본다. 여기서는 라우트가 그 화면에 제대로
 * 연결돼 있는지만 확인한다 — 자리표시자로 되돌아가면 바로 걸리도록.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: () => {}, push: () => {}, prefetch: () => {}, refresh: () => {} }),
  usePathname: () => "/me",
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPage(routes: (call: ApiCall) => Route) {
  stubApi((name, value) => vi.stubGlobal(name, value), routes);
  render(
    <SessionProvider>
      <MePage />
    </SessionProvider>,
  );
}

describe("/me", () => {
  test("탭 제목을 붙인다", () => {
    expect(metadata.title).toBe("내 정보");
  });

  test("로그인한 사용자의 요약을 보여준다", async () => {
    renderPage(okRoutes());

    expect(await screen.findByRole("heading", { level: 1, name: "충전러 님" })).toBeInTheDocument();
    expect(await screen.findByText("출퇴근 차")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeInTheDocument();
  });

  test("로그인하지 않았으면 로그인으로 안내한다", async () => {
    renderPage(() => ({ status: 401, body: { detail: "로그인이 필요합니다." } }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
  });
});

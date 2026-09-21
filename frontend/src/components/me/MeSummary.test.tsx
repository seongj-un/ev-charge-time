import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";

import { MeSummary } from "./MeSummary";
import {
  USER,
  WEEKEND,
  callsTo,
  okRoutes,
  stubApi,
  type ApiCall,
  type Route,
} from "./test-api";

/*
 * 이 화면이 지키는 약속.
 *   1) 로그인하지 않았으면 데이터를 지어내지 않고 로그인으로 보낸다.
 *   2) 백엔드에 닿지 못한 것과 로그인하지 않은 것을 섞지 않는다.
 *   3) 탈퇴는 비밀번호 재확인 없이는 한 글자도 서버로 나가지 않는다.
 * 나머지(색·여백)는 테스트하지 않는다 — 디자인이 바뀔 때마다 깨지기만 한다.
 */

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: replace, prefetch: () => {}, refresh: () => {} }),
  usePathname: () => "/me",
}));

afterEach(() => {
  vi.unstubAllGlobals();
  replace.mockClear();
});

function renderSummary(routes: (call: ApiCall) => Route): ApiCall[] {
  const calls = stubApi((name, value) => vi.stubGlobal(name, value), routes);
  render(
    <SessionProvider>
      <MeSummary />
    </SessionProvider>,
  );
  return calls;
}

describe("마이페이지 요약", () => {
  test("로그인하지 않았으면 로그인 화면으로 안내한다", async () => {
    renderSummary(() => ({ status: 401, body: { detail: "로그인이 필요합니다." } }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
    // 로그인하고 나면 보던 화면으로 돌아와야 한다.
    expect(screen.getByRole("link", { name: "로그인" })).toHaveAttribute(
      "href",
      "/login?next=%2Fme",
    );
  });

  test("서버에 닿지 못한 것을 로그인 문제로 둔갑시키지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    render(
      <SessionProvider>
        <MeSummary />
      </SessionProvider>,
    );

    expect(
      await screen.findByText("서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하세요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("로그인이 필요해요")).not.toBeInTheDocument();
  });

  test("닉네임·이메일과 기본 차량을 보여준다", async () => {
    renderSummary(okRoutes());

    expect(await screen.findByRole("heading", { level: 1, name: "충전러 님" })).toBeInTheDocument();
    expect(screen.getByText("driver@example.com")).toBeInTheDocument();
    expect(await screen.findByText("출퇴근 차")).toBeInTheDocument();
    expect(screen.getByText("70 kWh · 7 kW · 자가 저압")).toBeInTheDocument();
    // 기본이 아닌 차는 요약에 끼워 넣지 않는다.
    expect(screen.queryByText("주말 차")).not.toBeInTheDocument();
  });

  test("기본 차량이 없으면 차량 추가로 이끈다", async () => {
    renderSummary(okRoutes({ vehicles: [WEEKEND] }));

    expect(await screen.findByText("기본 차량이 아직 없어요")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "차량 등록하기" })).toHaveAttribute(
      "href",
      "/me/vehicles",
    );
  });

  test("이번 달 저장 건수와 절감 합계를 보여준다", async () => {
    const calls = renderSummary(
      okRoutes({ summary: { month: "2026-09", count: 3, total_savings_won: 12400 } }),
    );

    expect(await screen.findByText("3건")).toBeInTheDocument();
    expect(screen.getByText("12,400원")).toBeInTheDocument();

    // 달은 클라이언트에서 계산한다. 어떤 달이든 month 파라미터가 반드시 붙어야 한다.
    const summaryCall = calls.find((call) => call.url.startsWith("/api/me/plans/summary"));
    expect(summaryCall?.url).toMatch(/month=\d{4}-\d{2}/);
  });

  /*
   * 즐겨찾기 응답 모델이 지금 바뀌는 중이라 호출하지 않는다.
   * 숫자를 지어내 채우면 모델이 바뀐 날 조용히 틀린 값이 뜬다.
   */
  test("즐겨찾는 충전소는 준비 중으로 두고 부르지 않는다", async () => {
    const calls = renderSummary(okRoutes());
    await screen.findByText("출퇴근 차");

    expect(calls.some((call) => call.url.startsWith("/api/me/favorites"))).toBe(false);
    // 모바일 목록의 배지와 데스크톱 카드가 둘 다 준비 중임을 밝힌다.
    expect(screen.getAllByText("준비 중").length).toBeGreaterThan(0);
  });

  test("요청 도중 세션이 끊기면 로그인 안내로 떨어진다", async () => {
    renderSummary((call) => {
      // /api/me는 통과시키고(= 로그인 상태로 들어온다) 차량 요청에서 세션이 끊긴 상황
      if (call.url === "/api/me" && call.method === "GET") return { body: USER };
      return { status: 401, body: { detail: "로그인이 필요합니다." } };
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
  });

  describe("회원 탈퇴", () => {
    test("비밀번호 없이는 탈퇴 요청을 보내지 않는다", async () => {
      const user = userEvent.setup();
      const calls = renderSummary(okRoutes());
      await screen.findByText("출퇴근 차");

      await user.click(screen.getByRole("button", { name: "회원 탈퇴" }));
      // 확인 단계가 있어야 한다 — 누르자마자 계정이 사라지면 안 된다.
      expect(screen.getByLabelText("비밀번호")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "탈퇴하기" }));

      expect(callsTo(calls, "DELETE", "/api/me")).toHaveLength(0);
      expect(screen.getByText("비밀번호를 입력해 주세요.")).toBeInTheDocument();
    });

    test("비밀번호를 확인하면 탈퇴하고 홈으로 보낸다", async () => {
      const user = userEvent.setup();
      const calls = renderSummary(okRoutes());
      await screen.findByText("출퇴근 차");

      await user.click(screen.getByRole("button", { name: "회원 탈퇴" }));
      await user.type(screen.getByLabelText("비밀번호"), "pw123456");
      await user.click(screen.getByRole("button", { name: "탈퇴하기" }));

      await waitFor(() => expect(callsTo(calls, "DELETE", "/api/me")).toHaveLength(1));
      expect(callsTo(calls, "DELETE", "/api/me")[0].body).toEqual({ password: "pw123456" });
      await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    });

    test("비밀번호가 틀리면 계정을 지우지 않고 이유를 보여준다", async () => {
      const user = userEvent.setup();
      const routes = okRoutes();
      renderSummary((call) => {
        if (call.method === "DELETE" && call.url === "/api/me") {
          return { status: 400, body: { detail: "비밀번호가 올바르지 않습니다." } };
        }
        return routes(call);
      });
      await screen.findByText("출퇴근 차");

      await user.click(screen.getByRole("button", { name: "회원 탈퇴" }));
      await user.type(screen.getByLabelText("비밀번호"), "틀린비번");
      await user.click(screen.getByRole("button", { name: "탈퇴하기" }));

      expect(await screen.findByText("비밀번호가 올바르지 않습니다.")).toBeInTheDocument();
      expect(replace).not.toHaveBeenCalled();
    });
  });

  test("로그아웃하면 세션을 정리하고 홈으로 보낸다", async () => {
    const user = userEvent.setup();
    const calls = renderSummary(okRoutes());
    await screen.findByText("출퇴근 차");

    await user.click(screen.getByRole("button", { name: "로그아웃" }));

    await waitFor(() => expect(callsTo(calls, "POST", "/api/auth/logout")).toHaveLength(1));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  test("사이드바에서 마이페이지 안쪽 화면으로 갈 수 있다", async () => {
    renderSummary(okRoutes());
    await screen.findByText("출퇴근 차");

    const sidebar = within(screen.getByRole("navigation", { name: "마이페이지 메뉴" }));
    expect(sidebar.getByRole("link", { name: "내 차량" })).toHaveAttribute("href", "/me/vehicles");
    expect(sidebar.getByRole("link", { name: "충전 기록" })).toHaveAttribute("href", "/me/plans");
    expect(sidebar.getByRole("link", { name: "즐겨찾는 충전소" })).toHaveAttribute(
      "href",
      "/me/favorites",
    );
  });
});

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import type { SavedPlan } from "@/lib/api/types";

import { PlansScreen } from "./PlansScreen";

/*
 * 이 화면이 지켜야 하는 약속.
 *   1. 로그인하지 않았으면 빈 목록이 아니라 로그인 안내를 보여준다.
 *   2. 보여주는 금액·시각은 저장된 값 그대로다.
 *   3. 지운다고 말하기 전에 한 번 더 묻고, 지운 뒤에는 정말 사라진다.
 *   4. 아직 못 불러온 기록이 있으면 그 사실을 감추지 않는다.
 */

const replace = vi.fn();
let search = new URLSearchParams("month=2026-10");

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => search,
  usePathname: () => "/me/plans",
}));

const USER = {
  id: "u1",
  email: "user@example.com",
  nickname: "충전러",
  created_at: "2026-09-01T09:00:00+09:00",
};

function plan(overrides: Partial<SavedPlan> & { id: string }): SavedPlan {
  return {
    created_at: "2026-10-10T11:00:00+09:00",
    request: {
      battery_kwh: 70,
      charger_kw: 7,
      soc_now: 30,
      soc_target: 60,
      earliest_start: "2026-10-10T10:00",
      deadline: "2026-10-10T18:00",
      mode: "self_low",
    },
    result: {
      best: {
        start: "2026-10-10T11:00:00",
        end: "2026-10-10T14:00:00",
        energy_kwh: 21,
        cost_won: 1495,
        discounted_kwh: 21,
      },
      baseline_now: {
        start: "2026-10-10T10:00:00",
        end: "2026-10-10T13:00:00",
        energy_kwh: 21,
        cost_won: 2655,
        discounted_kwh: 0,
      },
      savings_won: 1160,
      candidates_checked: 9,
      assumptions: [],
      unverified_tariff_items: [],
    },
    tariff_version: "2026.1-draft",
    vehicle_name: null,
    ...overrides,
  };
}

const PLAN_A = plan({ id: "a" });
const PLAN_B = plan({
  id: "b",
  created_at: "2026-10-07T22:00:00+09:00",
  result: {
    ...PLAN_A.result,
    best: { ...PLAN_A.result.best, start: "2026-10-07T22:00:00", end: "2026-10-08T01:00:00", cost_won: 2373 },
    savings_won: 399,
  },
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Routes = {
  me?: () => Response | Promise<Response>;
  plans?: (url: string) => Response | Promise<Response>;
  summary?: (month: string) => Response | Promise<Response>;
  remove?: (id: string) => Response | Promise<Response>;
};

type Call = { url: string; method: string };

function stubFetch(routes: Routes = {}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });

      if (url === "/api/me") {
        return routes.me?.() ?? json(USER);
      }
      if (url.startsWith("/api/me/plans/summary")) {
        const month = new URL(url, "http://test").searchParams.get("month") ?? "";
        return (
          routes.summary?.(month) ??
          json({ month, count: 2, total_savings_won: 1559 })
        );
      }
      if (url.startsWith("/api/me/plans") && method === "DELETE") {
        const id = url.slice("/api/me/plans/".length);
        return routes.remove?.(id) ?? new Response(null, { status: 204 });
      }
      if (url.startsWith("/api/me/plans")) {
        return (
          routes.plans?.(url) ?? json({ items: [PLAN_A, PLAN_B], next_cursor: null })
        );
      }
      throw new Error(`테스트가 모르는 요청: ${method} ${url}`);
    }),
  );
  return calls;
}

function renderScreen() {
  return render(
    <SessionProvider>
      <PlansScreen />
    </SessionProvider>,
  );
}

beforeEach(() => {
  replace.mockClear();
  search = new URLSearchParams("month=2026-10");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("로그인하지 않았을 때", () => {
  test("빈 목록 대신 로그인 안내를 보여준다", async () => {
    stubFetch({ me: () => json({ detail: "로그인이 필요합니다." }, 401) });

    renderScreen();

    expect(await screen.findByText("로그인이 필요해요")).toBeInTheDocument();
    // 돌아올 곳을 달고 보낸다 — 로그인하면 보던 화면으로 돌아와야 한다.
    expect(screen.getByRole("link", { name: /로그인/ })).toHaveAttribute(
      "href",
      "/login?next=%2Fme%2Fplans%3Fmonth%3D2026-10",
    );
  });

  test("로그인 여부를 모르는 동안 기록을 요청하지 않는다", async () => {
    const calls = stubFetch({ me: () => json({ detail: "x" }, 401) });

    renderScreen();
    await screen.findByText("로그인이 필요해요");

    expect(calls.some((call) => call.url.startsWith("/api/me/plans"))).toBe(false);
  });

  /* 백엔드가 꺼진 것을 손님으로 단정하면 "로그인하세요"가 떠서 원인을 못 찾는다. */
  test("서버에 닿지 못하면 로그인하라고 말하지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    renderScreen();

    expect(await screen.findByText(/백엔드가 실행 중인지 확인하세요/)).toBeInTheDocument();
    expect(screen.queryByText("로그인이 필요해요")).not.toBeInTheDocument();
  });
});

describe("기록 목록", () => {
  test("요약과 기록을 저장된 값 그대로 보여준다", async () => {
    stubFetch();

    renderScreen();

    // 요약 두 칸
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("1,559원")).toBeInTheDocument();

    // 기록 카드 — 시각은 저장된 벽시계 값 그대로다 (표준시로 밀리면 안 된다).
    expect(screen.getByText("10월 10일 (토)")).toBeInTheDocument();
    expect(screen.getByText("11:00 – 14:00")).toBeInTheDocument();
    expect(screen.getByText("1,495원")).toBeInTheDocument();
    expect(screen.getByText("−1,160원")).toBeInTheDocument();

    expect(screen.getByText("10월 7일 (수)")).toBeInTheDocument();
    expect(screen.getByText("22:00 – 01:00")).toBeInTheDocument();
    expect(screen.getByText("−399원")).toBeInTheDocument();
  });

  /* 차량 이름은 응답에 없다. 지어내는 대신 저장된 조건을 되읽어 준다. */
  test("차량 이름을 지어내지 않고 저장된 조건을 보여준다", async () => {
    stubFetch();

    renderScreen();

    expect(await screen.findAllByText("70 kWh · 7 kW")).toHaveLength(2);
    expect(screen.queryByText("출퇴근 차")).not.toBeInTheDocument();
  });

  test("저장한 계획일 뿐 실제 충전 기록이 아니라고 밝힌다", async () => {
    stubFetch();

    renderScreen();

    expect(
      await screen.findByText(/저장한 계획이며 실제 충전 기록이 아니에요/),
    ).toBeInTheDocument();
  });

  test("기록이 하나도 없으면 추천받으러 갈 길을 준다", async () => {
    stubFetch({
      plans: () => json({ items: [], next_cursor: null }),
      summary: (month) => json({ month, count: 0, total_savings_won: 0 }),
    });

    renderScreen();

    expect(await screen.findByText("아직 저장한 계획이 없어요")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /추천/ })).toHaveAttribute("href", "/recommend");
  });
});

describe("월 선택", () => {
  test("URL의 달로 요약을 부른다", async () => {
    search = new URLSearchParams("month=2026-08");
    const calls = stubFetch();

    renderScreen();

    await waitFor(() =>
      expect(calls.map((call) => call.url)).toContain("/api/me/plans/summary?month=2026-08"),
    );
  });

  test("달을 바꾸면 URL을 갈아 끼운다", async () => {
    stubFetch();
    const user = userEvent.setup();

    renderScreen();
    const select = await screen.findByLabelText("월 선택");

    await user.selectOptions(select, "2026-09");

    expect(replace).toHaveBeenCalledWith("/me/plans?month=2026-09", { scroll: false });
  });

  test("달이 없으면 이번 달로 간다", async () => {
    search = new URLSearchParams();
    const calls = stubFetch();

    renderScreen();

    await waitFor(() => {
      const summary = calls.find((call) => call.url.startsWith("/api/me/plans/summary"));
      expect(summary?.url).toMatch(/month=\d{4}-\d{2}$/);
    });
  });
});

describe("아직 못 불러온 기록", () => {
  /*
   * 목록 API에 month 필터가 없어서 프론트에서 거른다. 커서 페이지네이션 탓에
   * 그 달 기록이 다음 페이지에 남아 있을 수 있다. 요약이 주는 그 달 전체 건수와
   * 화면에 뜬 건수를 맞대 보면 몇 건이 빠졌는지 정확히 말할 수 있다.
   */
  test("그 달 건수보다 적게 보여주고 있으면 숫자로 알린다", async () => {
    stubFetch({
      plans: () => json({ items: [PLAN_A], next_cursor: "c1" }),
      summary: (month) => json({ month, count: 5, total_savings_won: 3000 }),
    });

    renderScreen();

    expect(await screen.findByText(/5건 중 1건/)).toBeInTheDocument();
  });

  test("더 보기를 누르면 커서를 붙여 다음 페이지를 부른다", async () => {
    const calls = stubFetch({
      plans: (url) =>
        url.includes("cursor=c1")
          ? json({ items: [PLAN_B], next_cursor: null })
          : json({ items: [PLAN_A], next_cursor: "c1" }),
      summary: (month) => json({ month, count: 2, total_savings_won: 1559 }),
    });
    const user = userEvent.setup();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    await user.click(screen.getByRole("button", { name: "더 보기" }));

    expect(await screen.findByText("10월 7일 (수)")).toBeInTheDocument();
    expect(calls.map((call) => call.url)).toContain("/api/me/plans?limit=20&cursor=c1");
    // 다 불러왔으면 버튼이 사라진다.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "더 보기" })).not.toBeInTheDocument(),
    );
  });

  test("고른 달 기록이 아직 안 왔으면 빈 목록이라고 단정하지 않는다", async () => {
    stubFetch({
      plans: () => json({ items: [], next_cursor: "c1" }),
      summary: (month) => json({ month, count: 3, total_savings_won: 900 }),
    });

    renderScreen();

    expect(await screen.findByText(/아직 불러오지 않았어요/)).toBeInTheDocument();
    expect(screen.queryByText("아직 저장한 계획이 없어요")).not.toBeInTheDocument();
  });
});

describe("삭제", () => {
  test("확인 단계를 거친다", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    await user.click(screen.getByRole("button", { name: /10월 10일.*삭제/ }));

    expect(screen.getByText("정말 삭제할까요?")).toBeInTheDocument();
    // 확인 전에는 요청이 나가지 않는다.
    expect(calls.some((call) => call.method === "DELETE")).toBe(false);
  });

  test("취소하면 아무 일도 없다", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    await user.click(screen.getByRole("button", { name: /10월 10일.*삭제/ }));
    await user.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.queryByText("정말 삭제할까요?")).not.toBeInTheDocument();
    expect(screen.getByText("10월 10일 (토)")).toBeInTheDocument();
    expect(calls.some((call) => call.method === "DELETE")).toBe(false);
  });

  test("확인하면 지우고 목록에서 사라진다", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    await user.click(screen.getByRole("button", { name: /10월 10일.*삭제/ }));
    await user.click(screen.getByRole("button", { name: "네, 삭제할게요" }));

    await waitFor(() => expect(screen.queryByText("10월 10일 (토)")).not.toBeInTheDocument());
    expect(calls).toContainEqual({ url: "/api/me/plans/a", method: "DELETE" });
    // 남은 기록은 그대로 있다.
    expect(screen.getByText("10월 7일 (수)")).toBeInTheDocument();
  });

  /* 서버가 센 건수를 화면에서 빼면 서버와 어긋난다. 지운 뒤 요약을 다시 받는다. */
  test("지운 뒤 요약을 다시 받는다", async () => {
    let summaryCalls = 0;
    stubFetch({
      summary: (month) => {
        summaryCalls += 1;
        return json({ month, count: summaryCalls === 1 ? 2 : 1, total_savings_won: 399 });
      },
    });
    const user = userEvent.setup();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    await user.click(screen.getByRole("button", { name: /10월 10일.*삭제/ }));
    await user.click(screen.getByRole("button", { name: "네, 삭제할게요" }));

    await waitFor(() => expect(summaryCalls).toBe(2));
  });

  test("남의 기록이면 404를 그대로 알리고 목록을 건드리지 않는다", async () => {
    stubFetch({
      remove: () => json({ detail: "해당 기록을 찾을 수 없습니다." }, 404),
    });
    const user = userEvent.setup();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    await user.click(screen.getByRole("button", { name: /10월 10일.*삭제/ }));
    await user.click(screen.getByRole("button", { name: "네, 삭제할게요" }));

    expect(await screen.findByText(/해당 기록을 찾을 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByText("10월 10일 (토)")).toBeInTheDocument();
  });
});

describe("표 머리글", () => {
  test("데스크톱 표의 열 이름을 함께 둔다", async () => {
    stubFetch();

    renderScreen();
    await screen.findByText("10월 10일 (토)");

    const header = screen.getByTestId("plan-table-header");
    expect(within(header).getByText("저장일")).toBeInTheDocument();
    expect(within(header).getByText("차량")).toBeInTheDocument();
    expect(within(header).getByText("추천 시간")).toBeInTheDocument();
    expect(within(header).getByText("예상 비용")).toBeInTheDocument();
    expect(within(header).getByText("절감")).toBeInTheDocument();
  });
});

describe("목록을 못 불러왔을 때", () => {
  test("백엔드가 준 문장을 그대로 보여준다", async () => {
    stubFetch({ plans: () => json({ detail: "기록을 읽지 못했습니다." }, 500) });

    renderScreen();

    expect(await screen.findByText(/기록을 읽지 못했습니다/)).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { toSearchParams } from "@/lib/recommend-params";

import { ResultActions } from "./ResultActions";

/*
 * 저장 버튼이 지켜야 하는 약속.
 *   1. 미로그인일 때 저장된 척하지 않고, 돌아올 곳을 달고 로그인으로 보낸다.
 *   2. 같은 계획이 두 번 저장되지 않는다 (기록이 중복되면 절감 합계가 부풀려진다).
 *   3. 저장 뒤 보여주는 금액은 서버가 다시 계산해 돌려준 값이다.
 */

const QUERY = toSearchParams({
  batteryKwh: 70,
  chargerKw: 7,
  socNow: 30,
  socTarget: 60,
  earliestStart: "2026-10-07T18:00",
  deadline: "2026-10-08T08:00",
  mode: "self_low",
}).toString();

let search = new URLSearchParams(QUERY);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => search,
  usePathname: () => "/recommend/result",
}));

const USER = {
  id: "u1",
  email: "user@example.com",
  nickname: "충전러",
  created_at: "2026-09-01T09:00:00+09:00",
};

/** 서버가 다시 계산해 돌려주는 값. 화면이 들고 있던 금액과 일부러 다르게 둔다. */
const SAVED = {
  id: "plan-1",
  created_at: "2026-10-07T18:20:00+09:00",
  request: {
    battery_kwh: 70,
    charger_kw: 7,
    soc_now: 30,
    soc_target: 60,
    earliest_start: "2026-10-07T18:00",
    deadline: "2026-10-08T08:00",
    mode: "self_low",
  },
  result: {
    best: {
      start: "2026-10-07T22:00:00",
      end: "2026-10-08T01:00:00",
      energy_kwh: 21,
      cost_won: 2400,
      discounted_kwh: 0,
    },
    baseline_now: {
      start: "2026-10-07T18:00:00",
      end: "2026-10-07T21:00:00",
      energy_kwh: 21,
      cost_won: 2772,
      discounted_kwh: 0,
    },
    savings_won: 372,
    candidates_checked: 12,
    assumptions: [],
    unverified_tariff_items: [],
  },
  tariff_version: "2026.1-draft",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Call = { url: string; method: string; body: unknown };

function stubFetch(routes: {
  me?: () => Response | Promise<Response>;
  save?: () => Response | Promise<Response>;
}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({
        url,
        method,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      });
      if (url === "/api/me") return routes.me?.() ?? json({ detail: "x" }, 401);
      if (url === "/api/me/plans") return routes.save?.() ?? json(SAVED, 201);
      throw new Error(`테스트가 모르는 요청: ${method} ${url}`);
    }),
  );
  return calls;
}

function renderActions() {
  return render(
    <SessionProvider>
      <ResultActions />
    </SessionProvider>,
  );
}

beforeEach(() => {
  search = new URLSearchParams(QUERY);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("로그인하지 않았을 때", () => {
  test("왜 로그인해야 하는지 말하고, 돌아올 곳을 달아 보낸다", async () => {
    stubFetch({});

    renderActions();

    const link = await screen.findByRole("link", { name: "로그인하고 저장" });
    expect(link).toHaveAttribute(
      "href",
      `/login?next=${encodeURIComponent(`/recommend/result?${QUERY}`)}`,
    );
    expect(
      screen.getByText(/로그인하면 충전 기록에 쌓이고 달별 절감액을 볼 수 있어요/),
    ).toBeInTheDocument();
  });

  test("저장된 척하지 않는다", async () => {
    const calls = stubFetch({});

    renderActions();
    await screen.findByRole("link", { name: "로그인하고 저장" });

    expect(screen.queryByText(/저장했어요/)).not.toBeInTheDocument();
    expect(calls.some((call) => call.url === "/api/me/plans")).toBe(false);
  });
});

describe("로그인했을 때", () => {
  test("저장하면 서버가 다시 계산한 금액과 기록으로 가는 길을 보여준다", async () => {
    const calls = stubFetch({ me: () => json(USER) });
    const user = userEvent.setup();

    renderActions();
    const button = await screen.findByRole("button", { name: "충전 기록에 저장" });

    await user.click(button);

    expect(await screen.findByText(/저장했어요/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "충전 기록 보기" })).toHaveAttribute(
      "href",
      "/me/plans",
    );
    // 화면이 들고 있던 값이 아니라 응답의 result를 쓴다. 서버가 다시 계산하기 때문이다.
    expect(screen.getByText("2,400원")).toBeInTheDocument();
    expect(screen.getByText("−372원")).toBeInTheDocument();

    const save = calls.find((call) => call.url === "/api/me/plans");
    expect(save?.method).toBe("POST");
    // 저장 본문은 추천 요청과 같은 모양이고, URL의 조건 그대로다.
    expect(save?.body).toEqual({
      battery_kwh: 70,
      charger_kw: 7,
      soc_now: 30,
      soc_target: 60,
      earliest_start: "2026-10-07T18:00",
      deadline: "2026-10-08T08:00",
      mode: "self_low",
    });
  });

  /* 두 번 저장되면 기록이 중복되고 달별 절감 합계가 부풀려진다. */
  test("두 번 눌러도 요청은 한 번만 나간다", async () => {
    const calls = stubFetch({
      me: () => json(USER),
      save: () => new Promise<Response>(() => {}),
    });
    const user = userEvent.setup();

    renderActions();
    const button = await screen.findByRole("button", { name: "충전 기록에 저장" });

    await user.click(button);
    await user.click(button);

    expect(calls.filter((call) => call.url === "/api/me/plans")).toHaveLength(1);
    expect(button).toBeDisabled();
  });

  test("저장에 실패하면 백엔드가 준 문장을 보여준다", async () => {
    stubFetch({
      me: () => json(USER),
      save: () => json({ detail: "시간이 부족합니다: 충전에 7:00:00 필요." }, 422),
    });
    const user = userEvent.setup();

    renderActions();
    await user.click(await screen.findByRole("button", { name: "충전 기록에 저장" }));

    expect(await screen.findByText(/시간이 부족합니다/)).toBeInTheDocument();
    expect(screen.queryByText(/저장했어요/)).not.toBeInTheDocument();
    // 다시 시도할 수 있어야 한다.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "충전 기록에 저장" })).toBeEnabled(),
    );
  });

  /* 세션이 만료된 채로 저장을 누른 경우. "실패했습니다"로 끝내면 할 수 있는 일이 없다. */
  test("저장 중 세션이 끊기면 로그인으로 가는 길을 준다", async () => {
    stubFetch({
      me: () => json(USER),
      save: () => json({ detail: "로그인이 필요합니다." }, 401),
    });
    const user = userEvent.setup();

    renderActions();
    await user.click(await screen.findByRole("button", { name: "충전 기록에 저장" }));

    expect(await screen.findByRole("link", { name: "로그인하고 저장" })).toHaveAttribute(
      "href",
      `/login?next=${encodeURIComponent(`/recommend/result?${QUERY}`)}`,
    );
  });
});

describe("조건이 주소에 없을 때", () => {
  test("저장 버튼을 눌러도 반쪽짜리 요청을 보내지 않는다", async () => {
    search = new URLSearchParams("battery_kwh=70");
    const calls = stubFetch({ me: () => json(USER) });

    renderActions();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "충전 기록에 저장" })).toBeDisabled(),
    );

    expect(calls.some((call) => call.url === "/api/me/plans")).toBe(false);
  });
});

/*
 * 차량을 골라 추천받았으면 저장할 때 vehicle_id를 함께 보내야 한다.
 * 안 보내면 SavedPlan.vehicle_name이 항상 null이라, 충전 기록이 "어느 차로 세운
 * 계획인지"를 영영 모른다 (API 명세서 7-3).
 */
describe("차량을 고른 계획 저장", () => {
  const saveCalls = (calls: Call[]) =>
    calls.filter((call) => call.method === "POST" && call.url === "/api/me/plans");

  test("URL에 vehicle_id가 있으면 저장 요청에 함께 보낸다", async () => {
    search = new URLSearchParams(`${QUERY}&vehicle_id=v1`);
    const calls = stubFetch({ me: () => json(USER) });
    const user = userEvent.setup();

    renderActions();
    await user.click(await screen.findByRole("button", { name: "충전 기록에 저장" }));

    await waitFor(() => expect(saveCalls(calls)).toHaveLength(1));
    expect(saveCalls(calls)[0].body).toMatchObject({ vehicle_id: "v1" });
  });

  test("직접 입력이면 vehicle_id를 보내지 않는다", async () => {
    const calls = stubFetch({ me: () => json(USER) });
    const user = userEvent.setup();

    renderActions();
    await user.click(await screen.findByRole("button", { name: "충전 기록에 저장" }));

    await waitFor(() => expect(saveCalls(calls)).toHaveLength(1));
    expect(saveCalls(calls)[0].body).not.toHaveProperty("vehicle_id");
  });
});

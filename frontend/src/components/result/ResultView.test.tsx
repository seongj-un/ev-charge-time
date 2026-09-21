import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import type { RecommendResponse, TimelineResponse } from "@/lib/api/types";
import { toSearchParams } from "@/lib/recommend-params";

import { ResultView } from "./ResultView";

/*
 * 아래 저장 버튼(ResultActions)이 로그인 상태와 주소를 읽는다. 둘 다 앱 밖에서는
 * 못 구하니 세션 프로바이더로 감싸고 라우터만 가짜로 세운다.
 */
const router = vi.hoisted(() => ({ search: new URLSearchParams() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => router.search,
  usePathname: () => "/recommend/result",
}));

/** 조건의 정본은 URL이다 — 화면에 넘기는 쿼리를 주소에도 그대로 실어 둔다. */
function withSession(query: string) {
  router.search = new URLSearchParams(query);
  return (
    <SessionProvider>
      <ResultView query={query} />
    </SessionProvider>
  );
}

/*
 * 이 화면이 하는 약속은 두 가지다.
 *   1. 조건 → 추천 → 금액을 틀리지 않게 보여준다.
 *   2. 확정되지 않은 것을 확정처럼 보여주지 않는다.
 * 아래 테스트는 그 두 가지가 무너지는 경우를 잡는다.
 */

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const QUERY = toSearchParams({
  batteryKwh: 70,
  chargerKw: 7,
  socNow: 30,
  socTarget: 60,
  earliestStart: "2026-10-07T18:00",
  deadline: "2026-10-08T08:00",
  mode: "self_low",
}).toString();

const RECOMMENDATION: RecommendResponse = {
  best: {
    start: "2026-10-07T22:00:00",
    end: "2026-10-08T01:00:00",
    energy_kwh: 21,
    cost_won: 2373,
    discounted_kwh: 0,
  },
  baseline_now: {
    start: "2026-10-07T18:00:00",
    end: "2026-10-07T21:00:00",
    energy_kwh: 21,
    cost_won: 2772,
    discounted_kwh: 0,
  },
  savings_won: 399,
  candidates_checked: 12,
  assumptions: ["충전 출력 일정", "연속 충전", "기본요금 제외"],
  // 백엔드가 실제로 주는 모양 — 사람이 읽을 이름이 아니라 요금표 안의 키다.
  unverified_tariff_items: ["time_bands", "adders.fuel_adjustment_per_kwh"],
};

/**
 * 날짜마다 단가 자릿수를 다르게 준다 (7일은 1xx, 8일은 2xx).
 * 두 날짜에 같은 값을 주면 첫날 요금표로 둘째 날을 그려도 테스트가 통과한다.
 */
function timelineOf(day: string): TimelineResponse {
  const base = day === "2026-10-08" ? 200 : 100;
  return {
    day,
    mode: "self_low",
    season: "spring_fall",
    is_holiday: false,
    hours: Array.from({ length: 24 }, (_, hour) => ({
      hour,
      band:
        hour >= 22 || hour < 8
          ? ("light" as const)
          : hour === 21
            ? ("middle" as const)
            : ("peak" as const),
      discounted: false,
      price_per_kwh: base + hour,
    })),
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Routes = {
  recommend?: () => Response | Promise<Response>;
  timeline?: (day: string) => Response | Promise<Response>;
};

/** 화면이 두 엔드포인트를 부르므로 URL로 갈라 준다. */
function stubFetch(routes: Routes) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url === "/api/me") {
        // 세션 확인. 이 파일은 추천 화면 자체를 보므로 손님으로 고정한다.
        return jsonResponse({ detail: "로그인이 필요합니다." }, 401);
      }
      if (url.startsWith("/api/recommend")) {
        return routes.recommend?.() ?? jsonResponse(RECOMMENDATION);
      }
      if (url.startsWith("/api/timeline")) {
        const day = new URL(url, "http://test").searchParams.get("day") ?? "";
        return routes.timeline?.(day) ?? jsonResponse(timelineOf(day));
      }
      throw new Error(`테스트가 모르는 요청: ${url}`);
    }),
  );
  return calls;
}

describe("조건이 없을 때", () => {
  test("빈 쿼리면 요청하지 않고 조건 입력으로 안내한다", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(withSession(""));

    expect(screen.getByText("충전 조건이 없어요")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /충전 조건 입력/ })).toHaveAttribute(
      "href",
      "/recommend",
    );
    // 조건이 반쪽이면 요청 자체를 보내지 않는다 — 422를 받아 오류 화면을 띄우는 건 낭비다.
    // (세션 확인 /api/me는 프로바이더가 화면과 무관하게 한 번 부른다.)
    const asked = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(asked.filter((url) => url !== "/api/me")).toEqual([]);
  });

  test("조건이 하나라도 빠지면 마찬가지다", () => {
    vi.stubGlobal("fetch", vi.fn());

    render(withSession("battery_kwh=70&charger_kw=7"));

    expect(screen.getByText("충전 조건이 없어요")).toBeInTheDocument();
  });
});

describe("불러오는 중", () => {
  test("응답을 기다리는 동안 스켈레톤을 보여준다", () => {
    stubFetch({ recommend: () => new Promise<Response>(() => {}) });

    render(withSession(QUERY));

    expect(screen.getByRole("status")).toHaveTextContent("추천을 계산하고 있어요");
  });
});

describe("추천을 받았을 때", () => {
  test("추천 시각·비용·절감액을 보여준다", async () => {
    stubFetch({});

    render(withSession(QUERY));

    expect(await screen.findByText("01:00")).toBeInTheDocument();
    expect(screen.getAllByText("22:00").length).toBeGreaterThan(0);
    expect(screen.getByText("오늘 밤 시작 · 약 3시간 · 내일 08시 전 완료")).toBeInTheDocument();
    expect(screen.getByText("2,772원")).toBeInTheDocument();
    expect(screen.getByText("2,373원")).toBeInTheDocument();
    // 절감액은 빼기 기호(−)로 적는다. 하이픈이면 고정폭 숫자와 폭이 어긋난다.
    expect(screen.getByText("−399원")).toBeInTheDocument();
  });

  test("조건 요약을 배지로 되짚어 준다", async () => {
    stubFetch({});

    render(withSession(QUERY));

    expect(await screen.findByText("10월 7일 (수)")).toBeInTheDocument();
    expect(screen.getByText("자가 저압")).toBeInTheDocument();
    expect(screen.getByText("21 kWh")).toBeInTheDocument();
    expect(screen.getByText("7 kW")).toBeInTheDocument();
  });

  test("계산 가정을 이어 붙여 보여준다", async () => {
    stubFetch({});

    render(withSession(QUERY));

    expect(
      await screen.findByText("계산 가정: 충전 출력 일정 · 연속 충전 · 기본요금 제외"),
    ).toBeInTheDocument();
  });
});

describe("차트", () => {
  test("추천 구간이 걸친 날짜마다 timeline을 부른다", async () => {
    const calls = stubFetch({});

    render(withSession(QUERY));
    await screen.findByText("01:00");
    await screen.findByText("18시 → 다음날 08시");

    expect(calls).toContain("/api/timeline?day=2026-10-07&mode=self_low");
    expect(calls).toContain("/api/timeline?day=2026-10-08&mode=self_low");
  });

  test("두 날짜의 단가를 이어 붙여 18시부터 7시까지 그린다", async () => {
    stubFetch({});

    render(withSession(QUERY));

    // 막대는 시각·부하구간·단가를 읽을 수 있는 이름을 갖는다 (색만으로 알려주지 않는다).
    expect(
      await screen.findByRole("button", { name: "18시 · 최대 · 118.0원/kWh" }),
    ).toBeInTheDocument();
    // 0시 칸은 둘째 날(2xx) 요금표에서 와야 한다. 첫째 날을 두 번 쓰면 여기서 걸린다.
    expect(screen.getByRole("button", { name: "0시 · 경부하 · 200.0원/kWh" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "7시 · 경부하 · 207.0원/kWh" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^8시 ·/ })).not.toBeInTheDocument();
  });

  test("단가를 못 불러와도 추천은 그대로 보여주고 차트만 뺀다", async () => {
    stubFetch({ timeline: () => jsonResponse({ detail: "요금표를 읽지 못했습니다." }, 500) });

    render(withSession(QUERY));

    expect(await screen.findByText("2,373원")).toBeInTheDocument();
    expect(screen.getByText(/시간대별 단가를 불러오지 못했습니다/)).toBeInTheDocument();
  });
});

describe("정직함", () => {
  test("확인 전 요금 항목이 있으면 잠정치라고 고지한다", async () => {
    stubFetch({});

    render(withSession(QUERY));

    expect(
      await screen.findByText(/시간대 구분과 부가 요금은 공식 요금표 확인 전 값입니다/),
    ).toBeInTheDocument();
    // 어느 항목이 확인 전인지도 버리지 않는다.
    expect(screen.getByText(/확인 전 항목/)).toBeInTheDocument();
    expect(screen.getByText("adders.fuel_adjustment_per_kwh")).toBeInTheDocument();
  });

  test("확인 전 항목이 없으면 고지를 띄우지 않는다", async () => {
    stubFetch({
      recommend: () => jsonResponse({ ...RECOMMENDATION, unverified_tariff_items: [] }),
    });

    render(withSession(QUERY));
    await screen.findByText("2,373원");

    expect(screen.queryByText(/공식 요금표 확인 전 값입니다/)).not.toBeInTheDocument();
  });

  /*
   * 저장은 이제 진짜로 동작한다 (F-13). 손님일 때 저장된 척하지 않는다는 약속은 그대로다 —
   * 대신 준비 중이라고 말하는 게 아니라, 돌아올 곳을 달고 로그인으로 보낸다.
   * 저장 버튼 자체의 동작은 ResultActions.test.tsx가 따로 검사한다.
   */
  test("손님에게는 저장된 척하지 않고 로그인으로 보낸다", async () => {
    stubFetch({});

    render(withSession(QUERY));
    await screen.findByText("2,373원");

    expect(screen.getByRole("link", { name: "로그인하고 저장" })).toHaveAttribute(
      "href",
      `/login?next=${encodeURIComponent(`/recommend/result?${QUERY}`)}`,
    );
    expect(screen.queryByText(/저장했어요|저장되었습니다/)).not.toBeInTheDocument();
  });
});

describe("오류", () => {
  test("422면 백엔드가 준 detail을 그대로 보여준다", async () => {
    stubFetch({
      recommend: () =>
        jsonResponse(
          { detail: "시간이 부족합니다: 충전에 7:00:00 필요, 가능한 시간은 2:00:00." },
          422,
        ),
    });

    render(withSession(QUERY));

    expect(
      await screen.findByText(/시간이 부족합니다: 충전에 7:00:00 필요/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /조건 고치기/ })).toBeInTheDocument();
  });

  test("서버에 닿지 못하면 무엇을 확인해야 하는지 알려준다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    render(withSession(QUERY));

    expect(await screen.findByText(/백엔드가 실행 중인지 확인하세요/)).toBeInTheDocument();
  });
});

describe("조건이 바뀌었을 때", () => {
  test("다시 시도를 누르면 같은 조건으로 한 번 더 부른다", async () => {
    let attempt = 0;
    const calls = stubFetch({
      recommend: () => {
        attempt += 1;
        return attempt === 1
          ? jsonResponse({ detail: "요금표를 읽지 못했습니다." }, 500)
          : jsonResponse(RECOMMENDATION);
      },
    });
    const user = userEvent.setup();

    render(withSession(QUERY));
    await screen.findByText(/요금표를 읽지 못했습니다/);

    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByText("2,373원")).toBeInTheDocument();
    expect(calls.filter((url) => url.startsWith("/api/recommend"))).toHaveLength(2);
  });

  test("조건이 바뀌면 이전 조건의 금액을 그대로 두지 않는다", async () => {
    stubFetch({ recommend: () => new Promise<Response>(() => {}) });
    const { rerender } = render(withSession(QUERY));

    // 먼저 한 조건의 결과를 띄운다.
    stubFetch({});
    rerender(withSession(`${QUERY}&x=1`));
    await screen.findByText("2,373원");

    // 응답이 오지 않는 새 조건으로 바꾸면 옛 금액이 남아 있으면 안 된다.
    stubFetch({ recommend: () => new Promise<Response>(() => {}) });
    rerender(withSession(QUERY.replace("soc_target=60", "soc_target=80")));

    await waitFor(() => expect(screen.queryByText("2,373원")).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("추천을 계산하고 있어요");
  });
});

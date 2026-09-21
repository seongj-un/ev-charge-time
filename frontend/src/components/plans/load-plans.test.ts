import { afterEach, describe, expect, test, vi } from "vitest";

import type { SavedPlan } from "@/lib/api/types";

import { loadPlanPage } from "./load-plans";

afterEach(() => {
  vi.unstubAllGlobals();
});

function plan(id: string, createdAt: string): SavedPlan {
  return {
    id,
    created_at: createdAt,
    request: {
      battery_kwh: 70,
      charger_kw: 7,
      soc_now: 30,
      soc_target: 60,
      earliest_start: "2026-09-21T18:00",
      deadline: "2026-09-22T08:00",
      mode: "self_low",
    },
    result: {
      best: {
        start: "2026-09-21T22:00:00",
        end: "2026-09-22T01:00:00",
        energy_kwh: 21,
        cost_won: 2373,
        discounted_kwh: 0,
      },
      baseline_now: {
        start: "2026-09-21T18:00:00",
        end: "2026-09-21T21:00:00",
        energy_kwh: 21,
        cost_won: 2772,
        discounted_kwh: 0,
      },
      savings_won: 399,
      candidates_checked: 12,
      assumptions: [],
      unverified_tariff_items: [],
    },
    tariff_version: "2026.1-draft",
    vehicle_name: null,
    charge_start: "2026-09-21T22:00:00+09:00",
  };
}

function stubFetch(body: unknown) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return urls;
}

describe("loadPlanPage", () => {
  /*
   * 필터도 정렬도 서버가 한다. month는 충전 날짜(charge_start) 기준이다
   * (API 명세서 7-3). 프론트에서 거르던 시절에는 "그 달 기록이 다음 커서
   * 페이지에 있어 안 보이는" 구멍이 있었는데, 그건 화면에 한계를 적어 덮을
   * 문제가 아니라 API가 가져야 할 필터였다.
   */
  test("month를 API에 그대로 넘긴다", async () => {
    const urls = stubFetch({ items: [], next_cursor: null });

    await loadPlanPage({ month: "2026-10" });

    expect(urls[0]).toContain("month=2026-10");
  });

  /* limit=0은 지금 백엔드가 500을 낸다. 0을 보낼 여지를 아예 두지 않는다. */
  test("limit은 항상 1 이상이다", async () => {
    const urls = stubFetch({ items: [], next_cursor: null });

    await loadPlanPage({ month: "2026-10" });

    const limit = Number(new URL(urls[0], "http://test").searchParams.get("limit"));
    expect(limit).toBeGreaterThan(0);
  });

  test("커서를 그대로 이어 붙인다", async () => {
    const urls = stubFetch({ items: [], next_cursor: null });

    await loadPlanPage({ month: "2026-10", cursor: "c1" });

    expect(urls[0]).toContain("cursor=c1");
    expect(urls[0]).toContain("month=2026-10");
  });

  test("서버가 준 목록을 그대로 쓰고 커서를 넘긴다", async () => {
    // 서버가 이미 그 달만, 충전 날짜 내림차순으로 걸러 준다. 다시 거르거나
    // 다시 정렬하면 서버와 화면이 갈라진다.
    stubFetch({
      items: [
        plan("a", "2026-10-20T22:00:00+09:00"),
        plan("b", "2026-10-07T22:00:00+09:00"),
      ],
      next_cursor: "c2",
    });

    const page = await loadPlanPage({ month: "2026-10" });

    expect(page.items.map((item) => item.id)).toEqual(["a", "b"]);
    expect(page.nextCursor).toBe("c2");
  });
});

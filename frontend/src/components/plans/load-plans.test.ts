import { afterEach, describe, expect, test, vi } from "vitest";

import type { SavedPlan } from "@/lib/api/types";

import { loadPlanPage, PAGE_SIZE } from "./load-plans";

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
   * 목록 API에는 아직 month 필터가 없다. FastAPI는 모르는 쿼리 파라미터를 조용히
   * 무시하므로 month를 실어 보내면 "걸러진 것처럼 보이는 전체 목록"이 돌아온다.
   * 화면이 조용히 거짓말을 하는 것보다, 프론트에서 거르고 한계를 밝히는 편이 낫다.
   */
  test("month를 API에 보내지 않는다", async () => {
    const urls = stubFetch({ items: [], next_cursor: null });

    await loadPlanPage({ month: "2026-10" });

    expect(urls).toEqual([`/api/me/plans?limit=${PAGE_SIZE}`]);
    expect(urls[0]).not.toContain("month");
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

    expect(urls[0]).toBe(`/api/me/plans?limit=${PAGE_SIZE}&cursor=c1`);
  });

  test("받아 온 페이지에서 그 달 기록만 남기고, 원본 개수도 함께 알려준다", async () => {
    stubFetch({
      items: [
        plan("a", "2026-10-10T11:00:00+09:00"),
        plan("b", "2026-09-30T23:00:00+09:00"),
      ],
      next_cursor: "c2",
    });

    const page = await loadPlanPage({ month: "2026-10" });

    expect(page.items.map((item) => item.id)).toEqual(["a"]);
    expect(page.fetched).toBe(2);
    expect(page.nextCursor).toBe("c2");
  });
});

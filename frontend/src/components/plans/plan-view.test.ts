import { describe, expect, test } from "vitest";

import type { SavedPlan } from "@/lib/api/types";

import {
  currentMonth,
  filterByMonth,
  formatMonth,
  isMonth,
  monthOf,
  monthOptions,
  vehicleLabel,
} from "./plan-view";

function plan(overrides: Partial<SavedPlan> = {}): SavedPlan {
  return {
    id: "p1",
    created_at: "2026-09-21T17:04:06.133679+09:00",
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
    ...overrides,
  };
}

describe("isMonth", () => {
  test("YYYY-MM만 받는다", () => {
    expect(isMonth("2026-10")).toBe(true);
    expect(isMonth("2026-1")).toBe(false);
    expect(isMonth("2026-13")).toBe(false);
    expect(isMonth("2026-00")).toBe(false);
    expect(isMonth("2026-10-07")).toBe(false);
    expect(isMonth(null)).toBe(false);
  });
});

describe("monthOf", () => {
  test("백엔드가 주는 created_at에서 달을 읽는다", () => {
    expect(monthOf("2026-09-21T17:04:06.133679+09:00")).toBe("2026-09");
  });

  /*
   * new Date(created_at).getMonth()를 쓰면 UTC 환경에서 이 값이 9월 30일로 밀려
   * 10월 기록이 9월로 분류된다. 벽시계 값을 그대로 읽어야 한다.
   */
  test("자정 직후 기록이 앞 달로 밀리지 않는다", () => {
    expect(monthOf("2026-10-01T00:30:00+09:00")).toBe("2026-10");
  });
});

describe("currentMonth", () => {
  test("사용자 시계 기준 이번 달", () => {
    expect(currentMonth(new Date(2026, 9, 7, 3, 0))).toBe("2026-10");
    expect(currentMonth(new Date(2026, 0, 1, 0, 0))).toBe("2026-01");
  });
});

describe("monthOptions", () => {
  test("이번 달부터 과거로 12개를 준다", () => {
    const options = monthOptions(new Date(2026, 9, 7), "2026-10");
    expect(options).toHaveLength(12);
    expect(options[0]).toBe("2026-10");
    expect(options[11]).toBe("2025-11");
  });

  /* 링크로 받은 달이 목록에 없으면 <select>가 엉뚱한 달을 고른 것처럼 보인다. */
  test("고른 달이 12개월 밖이면 끼워 넣는다", () => {
    const options = monthOptions(new Date(2026, 9, 7), "2024-03");
    expect(options).toContain("2024-03");
    // 최신순이 유지된다.
    expect([...options].sort().reverse()).toEqual(options);
  });
});

describe("formatMonth", () => {
  test("2026년 10월", () => {
    expect(formatMonth("2026-10")).toBe("2026년 10월");
    expect(formatMonth("2026-01")).toBe("2026년 1월");
  });
});

describe("vehicleLabel", () => {
  /*
   * 응답에 차량 이름이 없다. 디자인의 "출퇴근 차"를 흉내 내려면 이름을 지어내야 하는데,
   * 없는 사실을 화면에 적는 건 금액을 틀리게 적는 것과 같은 종류의 거짓말이다.
   * 저장된 조건을 그대로 되읽어 준다.
   */
  test("차량 이름이 없으면 저장된 조건을 보여준다", () => {
    expect(vehicleLabel(plan())).toBe("70 kWh · 7 kW");
  });

  test("이름을 지어내지 않는다", () => {
    expect(vehicleLabel(plan())).not.toMatch(/차$/);
  });

  /* 백엔드가 vehicle_name을 넣기 전까지의 임시 표시. null이 정상값이라 폴백은 계속 필요하다. */
  test("등록 차량으로 저장한 기록은 그 사실만 덧붙인다", () => {
    const saved = plan();
    const withVehicle = {
      ...saved,
      request: { ...saved.request, vehicle_id: "v1" },
    } as SavedPlan;
    expect(vehicleLabel(withVehicle)).toBe("내 차량 · 70 kWh · 7 kW");
  });
});

describe("filterByMonth", () => {
  test("created_at이 그 달인 것만 남긴다", () => {
    const items = [
      plan({ id: "a", created_at: "2026-10-10T11:00:00+09:00" }),
      plan({ id: "b", created_at: "2026-09-30T23:59:00+09:00" }),
      plan({ id: "c", created_at: "2026-10-01T00:00:00+09:00" }),
    ];
    expect(filterByMonth(items, "2026-10").map((item) => item.id)).toEqual(["a", "c"]);
  });
});

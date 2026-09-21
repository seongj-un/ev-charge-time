import { describe, expect, test } from "vitest";

import type { SavedPlan } from "@/lib/api/types";

import {
  currentMonth,
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
    charge_start: "2026-09-21T22:00:00+09:00",
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
  /*
   * 충전 계획은 대개 **앞으로** 충전할 것이다. 월 기준이 충전 날짜로 바뀌었으므로
   * 과거만 주면 "오늘 세운 다음 달 계획"을 고를 수가 없다 — 저장하고도 못 찾는다.
   */
  test("앞으로 올 달도 고를 수 있다", () => {
    const options = monthOptions(new Date(2026, 8, 21), "2026-09");
    expect(options).toContain("2026-10");
    expect(options).toContain("2026-11");
  });

  test("이번 달을 포함해 12개를 최신순으로 준다", () => {
    const options = monthOptions(new Date(2026, 8, 21), "2026-09");
    expect(options).toHaveLength(12);
    expect(options).toContain("2026-09");
    expect([...options].sort().reverse()).toEqual(options);
  });

  test("과거도 충분히 남겨 둔다", () => {
    const options = monthOptions(new Date(2026, 8, 21), "2026-09");
    expect(options).toContain("2026-01");
  });

  /* 링크로 받은 달이 목록에 없으면 <select>가 엉뚱한 달을 고른 것처럼 보인다. */
  test("고른 달이 목록 밖이면 끼워 넣는다", () => {
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
   * 이름과 조건을 둘 다 보여준다. 차량을 고른 뒤 값을 고쳐 저장할 수 있어서,
   * 이름만 쓰면 사용자가 그 차의 제원 그대로 계산됐다고 읽는다.
   */
  test("이름이 있으면 조건과 함께 보여준다", () => {
    expect(vehicleLabel(plan({ vehicle_name: "출퇴근 차" }))).toBe(
      "출퇴근 차 · 70 kWh · 7 kW",
    );
  });

  test("고친 값이 있으면 이름이 아니라 그 값을 보여준다", () => {
    // 77 kWh 차를 골라 58로 고쳐 저장한 경우. 이름만 보이면 제원 그대로라고 오해한다.
    const edited = plan({
      vehicle_name: "출퇴근 차",
      request: { ...plan().request, battery_kwh: 58 },
    });
    expect(vehicleLabel(edited)).toBe("출퇴근 차 · 58 kWh · 7 kW");
  });

  /* 직접 입력하면 vehicle_name이 null이다 — 정상값이라 폴백은 계속 쓰인다. */
  test("이름이 없으면 저장된 조건만 보여준다", () => {
    expect(vehicleLabel(plan({ vehicle_name: null }))).toBe("70 kWh · 7 kW");
  });

  test("이름을 지어내지 않는다", () => {
    expect(vehicleLabel(plan({ vehicle_name: null }))).not.toMatch(/차$/);
  });

  test("빈 이름은 없는 것으로 친다", () => {
    expect(vehicleLabel(plan({ vehicle_name: "   " }))).toBe("70 kWh · 7 kW");
  });
});

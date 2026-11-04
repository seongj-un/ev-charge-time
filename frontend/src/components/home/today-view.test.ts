import { describe, expect, test } from "vitest";

import type { HourPrice } from "@/lib/api/types";

import { formatRun, hourInSeoul, hourRuns, summarizeDay } from "./today-view";

describe("hourRuns", () => {
  test("이어진 시각을 한 구간으로 묶는다", () => {
    expect(hourRuns([11, 12, 13, 14])).toEqual([{ start: 11, end: 15 }]);
  });

  test("자정을 넘는 구간은 하나로 잇는다", () => {
    expect(hourRuns([22, 23, 0, 1, 2, 3, 4, 5, 6, 7])).toEqual([{ start: 22, end: 8 }]);
    expect(formatRun({ start: 22, end: 8 })).toBe("22시–08시");
  });

  test("떨어진 구간은 따로 둔다", () => {
    expect(hourRuns([9, 10, 16, 17])).toEqual([
      { start: 9, end: 11 },
      { start: 16, end: 18 },
    ]);
  });

  test("하루 전체", () => {
    expect(hourRuns(Array.from({ length: 24 }, (_, hour) => hour))).toEqual([{ start: 0, end: 24 }]);
  });
});

describe("summarizeDay", () => {
  const hour = (h: number, band: HourPrice["band"], price: number, discounted = false): HourPrice => ({
    hour: h,
    band,
    price_per_kwh: price,
    discounted,
  });

  test("가장 싼·비싼 시간과 배수를 낸다", () => {
    const hours = Array.from({ length: 24 }, (_, h) =>
      h < 8 || h >= 22 ? hour(h, "light", 100) : h >= 18 && h < 21 ? hour(h, "peak", 250) : hour(h, "middle", 150),
    );
    const summary = summarizeDay(hours)!;
    expect(summary.minPrice).toBe(100);
    expect(summary.maxPrice).toBe(250);
    expect(summary.cheapest).toEqual([{ start: 22, end: 8 }]);
    expect(summary.priciest).toEqual([{ start: 18, end: 21 }]);
    expect(summary.ratio).toBeCloseTo(2.5);
  });

  test("할인이 걸린 시각은 할인 색이다", () => {
    const summary = summarizeDay([hour(12, "middle", 75, true)])!;
    expect(summary.cells[0].bandKey).toBe("discounted");
  });

  test("빈 응답이면 null", () => {
    expect(summarizeDay([])).toBeNull();
  });
});

test("hourInSeoul은 한국 시각이다", () => {
  // 2026-11-04T15:30Z = KST 00:30 (다음 날)
  expect(hourInSeoul(new Date("2026-11-04T15:30:00Z"))).toBe(0);
  expect(hourInSeoul(new Date("2026-11-04T03:00:00Z"))).toBe(12);
});

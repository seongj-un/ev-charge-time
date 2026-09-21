import { describe, expect, test } from "vitest";

import type { HourPrice, TimelineResponse } from "@/lib/api/types";

import {
  bandPriceRows,
  cheapestHours,
  dayTypeLabel,
  daySubtitle,
  discountRangeLabel,
  formatBandPrice,
  isDay,
  isMode,
  presentBandKeys,
  shiftDay,
  toColumns,
} from "./timeline-view";

/*
 * 화면에서 읽히는 문장과 막대는 전부 이 함수들에서 나온다.
 * 컴포넌트를 렌더링하지 않고도 "거짓말을 하는가"를 여기서 먼저 잡는다.
 */

function hour(partial: Partial<HourPrice> & { hour: number }): HourPrice {
  return {
    band: "light",
    discounted: false,
    price_per_kwh: 113.0,
    ...partial,
  };
}

describe("shiftDay", () => {
  test("하루 앞뒤로 옮긴다", () => {
    expect(shiftDay("2026-10-10", 1)).toBe("2026-10-11");
    expect(shiftDay("2026-10-10", -1)).toBe("2026-10-09");
  });

  test("달과 해를 넘어간다", () => {
    expect(shiftDay("2026-10-31", 1)).toBe("2026-11-01");
    expect(shiftDay("2026-01-01", -1)).toBe("2025-12-31");
  });

  test("윤년 2월을 안다", () => {
    expect(shiftDay("2028-02-28", 1)).toBe("2028-02-29");
  });
});

describe("isDay", () => {
  test("YYYY-MM-DD만 받는다", () => {
    expect(isDay("2026-10-10")).toBe(true);
    expect(isDay("2026-10-10T00:00")).toBe(false);
    expect(isDay("오늘")).toBe(false);
    expect(isDay(null)).toBe(false);
  });

  test("달력에 없는 날짜는 거른다", () => {
    // URL은 누구나 고칠 수 있다. 2월 30일을 그대로 백엔드에 보내면 422가 난다.
    expect(isDay("2026-02-30")).toBe(false);
    expect(isDay("2026-13-01")).toBe(false);
  });
});

describe("isMode", () => {
  test("아는 충전 방식만 받는다", () => {
    expect(isMode("self_low")).toBe(true);
    expect(isMode("public_fast")).toBe(true);
    expect(isMode("self_medium")).toBe(false);
    expect(isMode(null)).toBe(false);
  });
});

describe("toColumns", () => {
  test("할인이 걸린 시각은 부하구간과 상관없이 할인 색으로 간다", () => {
    const columns = toColumns([
      hour({ hour: 8, band: "middle", price_per_kwh: 126.4 }),
      hour({ hour: 11, band: "middle", discounted: true, price_per_kwh: 71.2 }),
    ]);

    expect(columns).toEqual([
      { hour: 8, bandKey: "middle", pricePerKwh: 126.4 },
      { hour: 11, bandKey: "discounted", pricePerKwh: 71.2 },
    ]);
  });
});

describe("cheapestHours", () => {
  test("최저 단가인 시각을 모두 모은다", () => {
    expect(
      cheapestHours([
        hour({ hour: 0, price_per_kwh: 113.0 }),
        hour({ hour: 1, price_per_kwh: 71.2 }),
        hour({ hour: 2, price_per_kwh: 71.2 }),
        hour({ hour: 3, price_per_kwh: 126.4 }),
      ]),
    ).toEqual([1, 2]);
  });

  test("부동소수 오차로 갈라진 같은 값은 같은 값으로 본다", () => {
    // 백엔드가 곱셈으로 만든 단가는 71.2와 71.20000000000001이 섞여 나온다.
    // 엄격 비교로 하나만 고르면 똑같이 싼 시각 하나가 마커에서 빠진다.
    expect(
      cheapestHours([
        hour({ hour: 1, price_per_kwh: 71.2 }),
        hour({ hour: 2, price_per_kwh: 71.20000000000001 }),
        hour({ hour: 3, price_per_kwh: 113.0 }),
      ]),
    ).toEqual([1, 2]);
  });

  test("시각이 없으면 빈 목록", () => {
    expect(cheapestHours([])).toEqual([]);
  });
});

describe("presentBandKeys", () => {
  test("실제로 나타난 구간만, 정해진 순서로 준다", () => {
    // 최대부하가 없는 날에 범례가 "최대"를 띄우면 범례를 읽을 수 없게 된다.
    expect(
      presentBandKeys([
        hour({ hour: 0, band: "light" }),
        hour({ hour: 8, band: "middle" }),
        hour({ hour: 11, band: "middle", discounted: true }),
      ]),
    ).toEqual(["light", "middle", "discounted"]);
  });
});

describe("bandPriceRows", () => {
  test("구간마다 한 줄씩, 값이 하나면 그 값", () => {
    expect(
      bandPriceRows([
        hour({ hour: 0, band: "light", price_per_kwh: 113.0 }),
        hour({ hour: 1, band: "light", price_per_kwh: 113.0 }),
        hour({ hour: 8, band: "middle", price_per_kwh: 126.4 }),
      ]),
    ).toEqual([
      { key: "light", min: 113.0, max: 113.0 },
      { key: "middle", min: 126.4, max: 126.4 },
    ]);
  });

  test("같은 구간에 값이 여러 개면 최소·최대를 함께 남긴다", () => {
    const rows = bandPriceRows([
      hour({ hour: 0, band: "light", price_per_kwh: 113.0 }),
      hour({ hour: 1, band: "light", price_per_kwh: 120.5 }),
      hour({ hour: 2, band: "light", price_per_kwh: 116.2 }),
    ]);

    expect(rows).toEqual([{ key: "light", min: 113.0, max: 120.5 }]);
  });
});

describe("formatBandPrice", () => {
  test("값이 하나면 한 숫자", () => {
    expect(formatBandPrice({ key: "light", min: 113.0, max: 113.0 })).toBe("113.0");
  });

  test("여러 값이면 범위로 보여준다", () => {
    expect(formatBandPrice({ key: "light", min: 113.0, max: 120.5 })).toBe("113.0–120.5");
  });

  test("소수 첫째 자리까지 같으면 범위로 쓰지 않는다", () => {
    // 113.00과 113.04는 화면에 둘 다 "113.0"이다. "113.0–113.0"은 정보가 아니라 잡음이다.
    expect(formatBandPrice({ key: "light", min: 113.0, max: 113.04 })).toBe("113.0");
  });
});

describe("discountRangeLabel", () => {
  test("할인이 걸린 시각을 이어 붙여 반개구간으로 읽는다", () => {
    // 11·12·13시가 할인이면 "11시부터 14시까지"다. 13시로 적으면 13시 한 시간이 사라진다.
    expect(
      discountRangeLabel([
        hour({ hour: 10 }),
        hour({ hour: 11, discounted: true }),
        hour({ hour: 12, discounted: true }),
        hour({ hour: 13, discounted: true }),
        hour({ hour: 14 }),
      ]),
    ).toBe("11–14시");
  });

  test("떨어진 구간이 둘이면 둘 다 적는다", () => {
    expect(
      discountRangeLabel([
        hour({ hour: 1, discounted: true }),
        hour({ hour: 2 }),
        hour({ hour: 3, discounted: true }),
      ]),
    ).toBe("1–2시, 3–4시");
  });

  test("할인이 없으면 null", () => {
    expect(discountRangeLabel([hour({ hour: 0 })])).toBeNull();
  });
});

describe("dayTypeLabel", () => {
  test("공휴일이 주말보다 앞선다", () => {
    expect(dayTypeLabel("2026-10-09", true)).toBe("공휴일");
  });

  test("토·일은 주말", () => {
    expect(dayTypeLabel("2026-10-10", false)).toBe("주말");
    expect(dayTypeLabel("2026-10-11", false)).toBe("주말");
  });

  test("그 밖은 평일", () => {
    expect(dayTypeLabel("2026-10-12", false)).toBe("평일");
  });
});

describe("daySubtitle", () => {
  test("응답의 계절·요일·공휴일에서 만든다", () => {
    const response = {
      day: "2026-10-10",
      mode: "self_low",
      season: "spring_fall",
      is_holiday: false,
      hours: [],
    } satisfies TimelineResponse;

    expect(daySubtitle(response)).toBe("시뮬레이션 · 봄·가을 주말");
  });

  test("겨울 평일이면 그렇게 적힌다", () => {
    const response = {
      day: "2026-01-14",
      mode: "self_low",
      season: "winter",
      is_holiday: false,
      hours: [],
    } satisfies TimelineResponse;

    expect(daySubtitle(response)).toBe("시뮬레이션 · 겨울 평일");
  });
});

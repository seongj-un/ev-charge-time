import { describe, expect, test } from "vitest";

import type { TimelineResponse } from "@/lib/api/types";

import { axisHours, axisRangeLabel, bandSummary, buildAxis, buildColumns } from "./chart-data";

/*
 * 차트 축은 0–23시 고정이 아니라 "시작 가능 시각 → 완료 시각"이다.
 * 디자인의 예시(18시 → 다음날 08시)는 자정을 넘고 두 날짜의 timeline이 필요하다.
 * 이 계산이 한 칸이라도 밀리면 "추천" 마커가 엉뚱한 막대 위에 얹힌다.
 */

/**
 * 날짜마다 단가 자릿수를 다르게 준다 (7일은 1xx, 8일은 2xx). 두 날짜에 같은 값을 넣으면
 * 첫날 요금표를 둘째 날에 재활용해도 테스트가 통과해 버린다 — 바로 그 실수를 잡으려는
 * 테스트라 값으로 날짜를 구분할 수 있어야 한다.
 */
function timelineOf(day: string, base: number): TimelineResponse {
  return {
    day,
    mode: "self_low",
    season: "spring_fall",
    is_holiday: false,
    hours: Array.from({ length: 24 }, (_, hour) => ({
      hour,
      band: hour >= 22 || hour < 8 ? ("light" as const) : hour === 21 ? ("middle" as const) : ("peak" as const),
      discounted: false,
      price_per_kwh: base + hour,
    })),
  };
}

describe("buildAxis", () => {
  test("18:00 시작 · 다음날 08:00 완료면 18시부터 7시까지 14칸", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-08T08:00",
    });

    expect(axis).not.toBeNull();
    expect(axis!.length).toBe(14);
    expect(axis!.startHour).toBe(18);
    expect(axis!.endHour).toBe(7);
    expect(axis!.days).toEqual(["2026-10-07", "2026-10-08"]);
  });

  test("같은 날 안에 끝나면 하루치 timeline만 부른다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T09:00",
      deadline: "2026-10-07T18:00",
    });

    expect(axis!.days).toEqual(["2026-10-07"]);
    expect(axis!.length).toBe(9);
    expect(axis!.endHour).toBe(17);
  });

  test("완료 시각에 분이 남아 있으면 그 시각 막대까지 축에 넣는다", () => {
    // 08:30 완료면 08시대에도 충전할 수 있다 — 8시 막대가 없으면 축이 거짓말을 한다.
    const axis = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-08T08:30",
    });

    expect(axis!.endHour).toBe(8);
    expect(axis!.length).toBe(15);
  });

  test("창이 24시간을 넘으면 24칸으로 자른다", () => {
    // PriceBarChart의 마커는 0–23 시각으로만 맞춘다. 축이 24시간을 넘으면
    // 같은 시각이 두 번 나와서 "추천" 표시가 엉뚱한 막대에도 찍힌다.
    const axis = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-09T20:00",
    });

    expect(axis!.length).toBe(24);
    expect(axis!.startHour).toBe(18);
    expect(axis!.endHour).toBe(17);
  });

  test("추천 구간이 24시간 창 밖이면 추천이 보이도록 창을 민다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-10T08:00",
      bestStart: "2026-10-09T02:00",
      bestEnd: "2026-10-09T05:00",
    });

    // 창이 추천 시작 시각으로 옮겨 붙고, 거기서 24시간이 이어진다.
    expect(axis!.startHour).toBe(2);
    expect(axis!.days).toEqual(["2026-10-09", "2026-10-10"]);
    expect(axis!.length).toBe(24);
  });

  test("완료가 시작보다 앞서면 축을 만들지 않는다", () => {
    expect(
      buildAxis({ earliestStart: "2026-10-07T18:00", deadline: "2026-10-07T17:00" }),
    ).toBeNull();
  });
});

describe("buildColumns", () => {
  test("두 날짜의 timeline을 이어 붙여 18시→7시 컬럼을 만든다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-08T08:00",
    })!;

    const columns = buildColumns(axis, [
      timelineOf("2026-10-07", 100),
      timelineOf("2026-10-08", 200),
    ]);

    expect(columns).toHaveLength(14);
    expect(columns.map((column) => column.hour)).toEqual([
      18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7,
    ]);
    // 자정 이후 칸은 둘째 날 timeline에서 와야 한다. 첫째 날을 두 번 이어 붙이면
    // 휴일·계절·주말 할인이 다른 날에는 차트가 통째로 틀린다.
    expect(columns[0].pricePerKwh).toBe(118);
    expect(columns[6].pricePerKwh).toBe(200);
    expect(columns[13].pricePerKwh).toBe(207);
    expect(columns[4].bandKey).toBe("light");
    expect(columns[3].bandKey).toBe("middle");
    expect(columns[0].bandKey).toBe("peak");
  });

  test("주말 할인이 걸린 시각은 부하구간 대신 할인으로 칠한다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-10T10:00",
      deadline: "2026-10-10T12:00",
    })!;
    const weekend = timelineOf("2026-10-10", 100);
    weekend.hours[10] = { hour: 10, band: "peak", discounted: true, price_per_kwh: 90 };

    const columns = buildColumns(axis, [weekend]);

    expect(columns[0].bandKey).toBe("discounted");
  });

  test("날짜 하나가 비면 그 칸은 비우고 나머지는 그린다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T22:00",
      deadline: "2026-10-08T02:00",
    })!;

    const columns = buildColumns(axis, [timelineOf("2026-10-07", 100)]);

    expect(columns.map((column) => column.hour)).toEqual([22, 23]);
  });
});

describe("axisRangeLabel", () => {
  test("자정을 넘으면 다음날이라고 적는다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-08T08:00",
    })!;

    expect(axisRangeLabel(axis)).toBe("18시 → 다음날 08시");
  });

  test("같은 날 안이면 날짜말을 붙이지 않는다", () => {
    const axis = buildAxis({
      earliestStart: "2026-10-07T09:00",
      deadline: "2026-10-07T18:00",
    })!;

    expect(axisRangeLabel(axis)).toBe("09시 → 18시");
  });
});

describe("bandSummary", () => {
  const axis = buildAxis({
    earliestStart: "2026-10-07T18:00",
    deadline: "2026-10-08T08:00",
  })!;
  const columns = buildColumns(axis, [
    timelineOf("2026-10-07", 100),
    timelineOf("2026-10-08", 200),
  ]);

  test("한 구간에만 걸리면 그 구간 이름", () => {
    expect(bandSummary(columns, [22, 23, 0])).toBe("경부하");
    expect(bandSummary(columns, [18, 19, 20])).toBe("최대부하");
  });

  test("여러 구간에 걸치면 '위주'를 붙인다", () => {
    // 세 시간 중 두 시간이 경부하라고 "경부하"라고 잘라 말하면 실제와 다르다.
    expect(bandSummary(columns, [21, 22, 23])).toBe("경부하 위주");
  });

  test("맞는 컬럼이 없으면 아무 말도 하지 않는다", () => {
    expect(bandSummary([], [22])).toBeNull();
  });
});

/*
 * 차트 마커는 막대를 시각(0–23)만으로 맞춘다. 그래서 구간을 시각으로만 넘기면
 * 오늘 22시의 "지금 바로"가 내일 22시 막대 위에 얹힌다. 축이 추천 쪽으로 밀려
 * 다음날부터 시작할 때 실제로 그랬다. 날짜까지 맞춰 축 안에 든 칸만 골라야 한다.
 */
describe("axisHours", () => {
  // 다음날 01시부터 24칸: 10월 8일 01–23시, 10월 9일 0시
  const axis = buildAxis({
    earliestStart: "2026-10-08T01:00",
    deadline: "2026-10-09T01:00",
  })!;

  test("다른 날짜의 같은 시각은 축에 표시하지 않는다", () => {
    // 오늘(7일) 22–24시 "지금 바로". 8일 22·23시 칸이 축에 있어도 그건 다른 날이다.
    expect(axisHours(axis, "2026-10-07T22:00:00+09:00", "2026-10-08T00:00:00+09:00")).toEqual(
      [],
    );
  });

  test("축 안에 든 칸은 그 시각으로 돌려준다", () => {
    expect(axisHours(axis, "2026-10-08T01:00:00+09:00", "2026-10-08T03:00:00+09:00")).toEqual([
      1, 2,
    ]);
    // 자정을 넘어도 축 안이면 이어서 센다. 정시 끝은 그 시각 칸을 쓰지 않는다.
    expect(axisHours(axis, "2026-10-08T23:00:00+09:00", "2026-10-09T01:00:00+09:00")).toEqual([
      23, 0,
    ]);
  });

  test("축에 걸친 부분만 남긴다", () => {
    // 7일 23시 – 8일 02:30. 7일 23시는 축 밖, 8일 1·2시는 축 안 (분이 남으면 그 칸까지).
    expect(axisHours(axis, "2026-10-07T23:00:00+09:00", "2026-10-08T02:30:00+09:00")).toEqual([
      1, 2,
    ]);
  });

  test("브라우저 표준시와 상관없이 KST 벽시계로 센다", () => {
    // TZ=UTC 기기에서 Date로 읽으면 22시가 13시가 된다. 표준시 표기를 그대로 믿어야 한다.
    const evening = buildAxis({
      earliestStart: "2026-10-07T18:00",
      deadline: "2026-10-08T08:00",
    })!;
    expect(
      axisHours(evening, "2026-10-07T22:00:00+09:00", "2026-10-08T01:00:00+09:00"),
    ).toEqual([22, 23, 0]);
  });

  test("다른 날짜의 시각으로 할인 설명을 붙이지 않는다", () => {
    // 8일 밤 22·23시만 주말 할인. 7일 밤 22·23시 "지금 바로"에 그 설명이 붙으면 거짓말이다.
    const nextDay = timelineOf("2026-10-08", 200);
    nextDay.hours[22] = { hour: 22, band: "light", discounted: true, price_per_kwh: 90 };
    nextDay.hours[23] = { hour: 23, band: "light", discounted: true, price_per_kwh: 90 };
    const columns = buildColumns(axis, [nextDay, timelineOf("2026-10-09", 300)]);

    const baseline = axisHours(axis, "2026-10-07T22:00:00+09:00", "2026-10-08T00:00:00+09:00");
    expect(bandSummary(columns, baseline)).toBeNull();

    const sameNight = axisHours(axis, "2026-10-08T22:00:00+09:00", "2026-10-09T00:00:00+09:00");
    expect(bandSummary(columns, sameNight)).toBe("주말 할인");
  });
});

import { describe, expect, test } from "vitest";

import {
  formatHm,
  formatKoreanDate,
  formatPricePerKwh,
  formatSignedWon,
  formatWon,
  parseKstWallClock,
} from "./format";

/*
 * 백엔드는 시각을 항상 +09:00을 달아 보낸다 (API 명세서 1장).
 * 그래서 Date로 넘겨 브라우저 표준시로 다시 읽지 않고, 문자열에 적힌
 * 벽시계 값을 그대로 쓴다. 심사위원 노트북이 어느 표준시든 22:00은 22:00이다.
 */
describe("parseKstWallClock", () => {
  test("+09:00이 달린 시각의 벽시계 값을 그대로 읽는다", () => {
    expect(parseKstWallClock("2026-10-07T22:00:00+09:00")).toEqual({
      year: 2026,
      month: 10,
      day: 7,
      hour: 22,
      minute: 0,
    });
  });

  test("표준시 표기가 없는 시각도 같은 벽시계로 읽는다", () => {
    expect(parseKstWallClock("2026-10-08T08:00")).toEqual({
      year: 2026,
      month: 10,
      day: 8,
      hour: 8,
      minute: 0,
    });
  });

  test("브라우저 표준시와 무관하게 읽는다", () => {
    // UTC 기준으로 읽었다면 13:00이 됐을 시각
    expect(parseKstWallClock("2026-10-07T22:00:00+09:00").hour).toBe(22);
  });
});

describe("formatHm", () => {
  test("시:분 두 자리로 맞춘다", () => {
    expect(formatHm("2026-10-08T01:00:00+09:00")).toBe("01:00");
  });

  test("자정을 24:00이 아니라 00:00으로 쓴다", () => {
    expect(formatHm("2026-10-08T00:00:00+09:00")).toBe("00:00");
  });
});

describe("formatKoreanDate", () => {
  test("월·일과 요일을 함께 쓴다", () => {
    // 2026-10-07은 수요일
    expect(formatKoreanDate("2026-10-07T18:00:00+09:00")).toBe("10월 7일 (수)");
  });

  test("토요일도 맞게 쓴다", () => {
    expect(formatKoreanDate("2026-10-10")).toBe("10월 10일 (토)");
  });
});

describe("formatWon", () => {
  test("천 단위를 끊는다", () => {
    expect(formatWon(2373)).toBe("2,373원");
  });

  test("천 원 미만은 끊지 않는다", () => {
    expect(formatWon(399)).toBe("399원");
  });

  test("0원도 쓴다", () => {
    expect(formatWon(0)).toBe("0원");
  });
});

describe("formatSignedWon", () => {
  test("절감액은 빼기 기호를 앞에 붙인다", () => {
    // 하이픈(-)이 아니라 빼기 기호(−). 고정폭에서 숫자와 폭이 맞는다.
    expect(formatSignedWon(399)).toBe("−399원");
  });

  test("절감이 없으면 부호를 붙이지 않는다", () => {
    expect(formatSignedWon(0)).toBe("0원");
  });
});

describe("formatPricePerKwh", () => {
  test("단가는 소수 첫째 자리까지 쓴다", () => {
    expect(formatPricePerKwh(113)).toBe("113.0");
  });

  test("둘째 자리에서 반올림한다", () => {
    expect(formatPricePerKwh(126.44)).toBe("126.4");
  });
});

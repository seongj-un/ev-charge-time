import { describe, expect, test } from "vitest";

import { parseDecimal } from "./number";

describe("parseDecimal", () => {
  test.each([
    ["70", 70],
    ["70.5", 70.5],
    [" 7 ", 7],
    [".5", 0.5],
    ["-5", -5],
  ])("'%s' → %s", (raw, expected) => {
    expect(parseDecimal(raw)).toBe(expected);
  });

  test.each(["", " ", "1e3", "0x10", "Infinity", "NaN", "7,5", "70kWh", "--1"])("'%s'는 숫자가 아니다", (raw) => {
    expect(parseDecimal(raw)).toBeNull();
  });
});

import { describe, expect, test } from "vitest";

import { unverifiedNotice } from "./tariff";

/*
 * 고정 문장은 요금표가 바뀌는 순간 틀린다. 실제로 그랬다 —
 * "시간대 구분과 부가 요금은 확인 전"이라고 적어 뒀는데 한전 공식 요금표가
 * 들어오면서 시간대 구분도 부가 요금도 확정됐고, 문장만 남아 거짓말이 됐다.
 * 그래서 백엔드가 주는 항목에서 문장을 만든다.
 */
describe("unverifiedNotice", () => {
  test("실제로 남은 항목만 우리말로 말한다", () => {
    expect(
      unverifiedNotice([
        "public_fast.base_price_per_kwh",
        "public_fast.weekend_discount",
        "weekend_discount_self",
      ]),
    ).toBe("공공 급속 단가와 주말 할인은 공식 요금표 확인 전 값입니다.");
  });

  test("항목이 하나면 그것만 말한다", () => {
    expect(unverifiedNotice(["weekend_discount_self"])).toBe(
      "주말 할인은 공식 요금표 확인 전 값입니다.",
    );
  });

  test("시간대 구분이 남아 있으면 그것도 말한다", () => {
    expect(unverifiedNotice(["time_bands"])).toBe(
      "시간대 구분은 공식 요금표 확인 전 값입니다.",
    );
  });

  /*
   * 조사는 앞 글자 받침에 따라 갈린다. 하나로 고정하면 "단가은", "구분와" 같은
   * 문장이 사용자에게 그대로 보인다 — 고지문이 깨진 한국어면 신뢰를 잃는다.
   */
  test("받침에 따라 조사를 고른다", () => {
    // 단가: 받침 없음 → 는
    expect(unverifiedNotice(["public_fast.base_price_per_kwh"])).toBe(
      "공공 급속 단가는 공식 요금표 확인 전 값입니다.",
    );
    // 구분: 받침 있음 → 과
    expect(unverifiedNotice(["time_bands", "weekend_discount_self"])).toBe(
      "시간대 구분과 주말 할인은 공식 요금표 확인 전 값입니다.",
    );
  });

  /*
   * 2026-04-16 요금 개편을 반영하면서 남은 미확인 항목이 둘로 줄었다.
   * 주말 할인 자체는 공식 문서로 확인됐고, 2030년까지라는 일몰 연도만
   * 근거가 없어 weekend_discount_sunset 으로 따로 떨어져 나왔다.
   *
   * "일부 요금 항목"으로 뭉뚱그리면 사용자는 무엇이 잠정치인지 모른다 —
   * 지금 화면에 실제로 뜨는 문장이라 이름을 붙여 준다.
   */
  test("주말 할인 적용 기한을 이름으로 말한다", () => {
    expect(unverifiedNotice(["weekend_discount_sunset"])).toBe(
      "주말 할인 적용 기한은 공식 요금표 확인 전 값입니다.",
    );
  });

  /** 지금 백엔드가 실제로 보내는 두 항목. */
  test("현재 남은 두 항목을 그대로 문장으로 만든다", () => {
    expect(
      unverifiedNotice(["public_fast.base_price_per_kwh", "weekend_discount_sunset"]),
    ).toBe("공공 급속 단가와 주말 할인 적용 기한은 공식 요금표 확인 전 값입니다.");
  });

  /* 백엔드가 새 키를 추가해도 빈 문장이 나오면 안 된다. */
  test("모르는 키는 뭉뚱그려 말한다", () => {
    expect(unverifiedNotice(["brand_new_thing"])).toBe(
      "일부 요금 항목은 공식 요금표 확인 전 값입니다.",
    );
  });

  test("아는 키와 모르는 키가 섞이면 둘 다 말한다", () => {
    expect(unverifiedNotice(["weekend_discount_self", "brand_new_thing"])).toContain("주말 할인");
    expect(unverifiedNotice(["weekend_discount_self", "brand_new_thing"])).toContain("일부 요금 항목");
  });

  test("남은 항목이 없으면 고지하지 않는다", () => {
    expect(unverifiedNotice([])).toBeNull();
  });
});

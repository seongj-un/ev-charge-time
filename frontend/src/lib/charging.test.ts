import { describe, expect, test } from "vitest";

import { coveredHours, estimateHours, requiredEnergyKwh } from "./charging";

/*
 * 필요 충전량과 소요 시간은 백엔드가 계산하지만, 입력 화면이 "최적 시간 찾기"를
 * 누르기 전에 "21 kWh · 약 3시간"을 먼저 보여준다. 그래서 같은 식을 프론트에도
 * 둔다 (백엔드 설계서: 필요량 = 용량 × (목표−현재) / 100 / 효율).
 */
describe("requiredEnergyKwh", () => {
  test("용량과 충전량 차이로 필요한 에너지를 낸다", () => {
    // 70 kWh 배터리를 30% → 60%: 70 × 0.3 = 21
    expect(
      requiredEnergyKwh({ batteryKwh: 70, socNow: 30, socTarget: 60 }),
    ).toBeCloseTo(21);
  });

  test("효율이 1보다 작으면 더 많이 넣어야 한다", () => {
    expect(
      requiredEnergyKwh({
        batteryKwh: 70,
        socNow: 30,
        socTarget: 60,
        efficiency: 0.9,
      }),
    ).toBeCloseTo(21 / 0.9);
  });

  test("목표가 현재보다 낮으면 0이다", () => {
    expect(
      requiredEnergyKwh({ batteryKwh: 70, socNow: 60, socTarget: 30 }),
    ).toBe(0);
  });
});

describe("estimateHours", () => {
  test("필요량을 충전기 출력으로 나눈다", () => {
    expect(estimateHours({ energyKwh: 21, chargerKw: 7 })).toBeCloseTo(3);
  });

  test("출력이 0이면 계산하지 않는다", () => {
    expect(estimateHours({ energyKwh: 21, chargerKw: 0 })).toBeNull();
  });
});

/*
 * 차트 위에 "추천 구간"과 "지금 바로 구간" 마커를 그리려면 그 구간이 몇 시
 * 막대들을 덮는지 알아야 한다. 자정을 넘는 구간이 흔하다 (22:00 – 01:00).
 */
describe("coveredHours", () => {
  test("구간이 걸친 시각들을 돌려준다", () => {
    expect(
      coveredHours("2026-10-07T18:00:00+09:00", "2026-10-07T21:00:00+09:00"),
    ).toEqual([18, 19, 20]);
  });

  test("자정을 넘으면 0시부터 이어 센다", () => {
    expect(
      coveredHours("2026-10-07T22:00:00+09:00", "2026-10-08T01:00:00+09:00"),
    ).toEqual([22, 23, 0]);
  });

  test("한 시간 안에서 끝나는 구간도 그 시각을 덮는다", () => {
    expect(
      coveredHours("2026-10-07T22:15:00+09:00", "2026-10-07T22:45:00+09:00"),
    ).toEqual([22]);
  });

  test("정시에 끝나면 그 시각은 덮지 않는다", () => {
    // 21:00에 끝났으면 21시 막대는 쓰지 않은 것이다
    expect(
      coveredHours("2026-10-07T20:00:00+09:00", "2026-10-07T21:00:00+09:00"),
    ).toEqual([20]);
  });

  test("분 단위로 걸치면 그 시각도 덮는다", () => {
    expect(
      coveredHours("2026-10-07T20:00:00+09:00", "2026-10-07T21:30:00+09:00"),
    ).toEqual([20, 21]);
  });
});

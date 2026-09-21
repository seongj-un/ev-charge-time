import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { SolarHour } from "@/lib/api/types";

import { SolarOverlay } from "./SolarOverlay";

/*
 * 태양광 예측을 단가 차트에 겹친다.
 *
 * **단가와 일사량을 같은 y축에 올리지 않는다.** 원/kWh와 W/m²는 단위가 달라서
 * 한 축에 올리면 이중축 차트가 되는데, 그건 두 계열의 상대 높이를 눈금 선택으로
 * 마음대로 바꿀 수 있다는 뜻이다. output_index가 0~1로 정규화돼 오는 이유이고,
 * 그래서 이 오버레이는 자기 높이 안에서만 그려진다.
 */

function hour(h: number, index: number): SolarHour {
  return {
    hour: h,
    ghi_wm2: index * 1000,
    clear_sky_ghi_wm2: 1000,
    output_index: index,
    predicted_mwh: null,
    sky: "1",
    pty: "0",
  };
}

/** 라이브 확인값(2026-09-22 전남, 맑음)을 옮긴 것 */
const CLEAR_DAY: SolarHour[] = [
  hour(3, 0),
  hour(9, 0.531),
  hour(12, 0.811),
  hour(15, 0.504),
  hour(21, 0),
];

const ASSUMPTIONS = [
  "전남 전체를 5km 격자 한 칸(nx=51, ny=67)으로 대신함",
  "설비용량 자료가 없어 지역 발전량(MWh)은 계산하지 않음",
];

describe("SolarOverlay", () => {
  test("시각마다 예측값을 하나씩 그린다", () => {
    const { container } = render(
      <SolarOverlay hours={CLEAR_DAY} columns={[3, 9, 12, 15, 21]} assumptions={[]} />,
    );
    expect(container.querySelectorAll("[data-solar-point]")).toHaveLength(5);
  });

  test("차트에 없는 시각은 그리지 않는다", () => {
    // 추천 결과 차트는 18시→다음날 08시처럼 일부 시각만 쓴다.
    const { container } = render(
      <SolarOverlay hours={CLEAR_DAY} columns={[9, 12]} assumptions={[]} />,
    );
    expect(container.querySelectorAll("[data-solar-point]")).toHaveLength(2);
  });

  test("예측이 없는 시각은 빈칸으로 둔다", () => {
    // 없는 값을 0으로 그리면 "그 시각엔 해가 없다"는 거짓이 된다.
    const { container } = render(
      <SolarOverlay hours={[hour(12, 0.8)]} columns={[11, 12, 13]} assumptions={[]} />,
    );
    expect(container.querySelectorAll("[data-solar-point]")).toHaveLength(1);
  });

  test("높이가 지수에 비례한다", () => {
    const { container } = render(
      <SolarOverlay hours={CLEAR_DAY} columns={[3, 12]} assumptions={[]} />,
    );
    const points = [...container.querySelectorAll<HTMLElement>("[data-solar-point]")];
    expect(points[0].style.height).toBe("0%");
    expect(points[1].style.height).toBe("81.1%");
  });

  /*
   * "전남 전체를 5km 격자 한 칸으로 대신함" 같은 한계는 사용자가 절대 짐작할 수
   * 없다. 안 보여주면 정밀한 지역 예측이라고 읽는다 — unverified_tariff_items와
   * 같은 성격이라 같은 방식으로 다룬다.
   */
  test("전제를 화면에 그대로 보여준다", () => {
    render(<SolarOverlay hours={CLEAR_DAY} columns={[12]} assumptions={ASSUMPTIONS} />);
    const note = screen.getByRole("note");
    expect(within(note).getByText(/5km 격자 한 칸/)).toBeInTheDocument();
    expect(within(note).getByText(/설비용량 자료가 없어/)).toBeInTheDocument();
  });

  test("전제가 없으면 빈 상자를 만들지 않는다", () => {
    render(<SolarOverlay hours={CLEAR_DAY} columns={[12]} assumptions={[]} />);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  test("값을 글자로도 읽을 수 있다", () => {
    // 색과 높이만으로 정보를 주지 않는다 — 차트 전체에 적용한 원칙이다.
    render(<SolarOverlay hours={CLEAR_DAY} columns={[12]} assumptions={[]} />);
    expect(
      screen.getByRole("img", { name: /12시.*태양광.*81/ }),
    ).toBeInTheDocument();
  });
});

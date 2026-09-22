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

/*
 * 2026-09-21 20:00 발표 응답에서 그대로 옮긴 세 줄.
 *
 * 길이를 가정하지 않는다 — 지역이 늘거나 전제가 추가되면 서버가 줄을 더 싣는다.
 * 그래서 컴포넌트는 배열을 순회만 하고, 이 상수는 문구를 검사하는 게 아니라
 * "서버가 준 줄이 빠짐없이 나오는지"를 확인하는 데 쓴다.
 */
const ASSUMPTIONS = [
  "전남 전체를 기상청 5km 격자 한 칸(nx=57, ny=71)의 예보로 대신합니다.",
  "기상청 단기예보 20260921 2000 발표를 사용했습니다.",
  "지역 태양광 설비용량 자료가 없어 predicted_mwh는 비워 둡니다. 일사량(ghi_wm2)과 STC 대비 지수(output_index)는 그대로 유효합니다.",
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
  test("전제를 한 줄도 빠뜨리지 않고 보여준다", () => {
    render(<SolarOverlay hours={CLEAR_DAY} columns={[12]} assumptions={ASSUMPTIONS} />);
    const note = screen.getByRole("note");
    expect(within(note).getAllByRole("listitem")).toHaveLength(ASSUMPTIONS.length);
    for (const line of ASSUMPTIONS) {
      expect(within(note).getByText(new RegExp(escapeRegExp(line)))).toBeInTheDocument();
    }
  });

  /*
   * 발표 회차 줄이 빠지면 안 된다. 예보는 하루 8번만 갱신돼서 화면의 값이 몇
   * 시간 전 발표일 수 있고, 사용자는 그걸 알아야 "왜 창밖과 다르지"를 납득한다.
   */
  test("어느 발표를 썼는지 보여준다", () => {
    render(<SolarOverlay hours={CLEAR_DAY} columns={[12]} assumptions={ASSUMPTIONS} />);
    expect(within(screen.getByRole("note")).getByText(/20260921 2000 발표/)).toBeInTheDocument();
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

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

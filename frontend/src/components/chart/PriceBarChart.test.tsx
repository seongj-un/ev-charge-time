import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { BandLegend, PriceBarChart, type PriceColumn } from "./PriceBarChart";

const COLUMNS: PriceColumn[] = [
  { hour: 18, bandKey: "peak", pricePerKwh: 132.0 },
  { hour: 19, bandKey: "peak", pricePerKwh: 132.0 },
  { hour: 20, bandKey: "middle", pricePerKwh: 126.4 },
  { hour: 21, bandKey: "light", pricePerKwh: 113.0 },
  { hour: 22, bandKey: "discounted", pricePerKwh: 66.0 },
];

describe("PriceBarChart", () => {
  test("시각마다 막대를 하나씩 그린다", () => {
    render(<PriceBarChart columns={COLUMNS} />);
    expect(screen.getAllByRole("button")).toHaveLength(COLUMNS.length);
  });

  /*
   * 부하구간 색 중 둘은 흰 배경 대비가 3:1 아래다. 색만으로 정보를 주면
   * 그 두 구간이 사실상 안 읽힌다. 막대마다 글자로 읽히는 이름이 있어야 한다.
   */
  test("막대마다 시각·부하구간·단가를 글자로 읽을 수 있다", () => {
    render(<PriceBarChart columns={COLUMNS} />);
    expect(
      screen.getByRole("button", { name: "18시 · 최대 · 132.0원/kWh" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "22시 · 주말 할인 · 66.0원/kWh" }),
    ).toBeInTheDocument();
  });

  test("같은 데이터를 표로도 제공한다", () => {
    render(<PriceBarChart columns={COLUMNS} />);
    const table = screen.getByRole("table", { name: /시간별 단가/ });
    expect(within(table).getAllByRole("row")).toHaveLength(COLUMNS.length + 1);
  });

  /*
   * 막대 높이는 0을 바닥으로 단가에 비례해야 한다. 축을 자르면 66원과 132원이
   * 몇 배 차이처럼 보인다 — 절감액을 주장하는 화면에서 그건 과장이다.
   */
  test("막대 높이가 0을 바닥으로 단가에 비례한다", () => {
    render(<PriceBarChart columns={COLUMNS} />);
    const tallest = screen.getByRole("button", { name: /^18시/ });
    const half = screen.getByRole("button", { name: /^22시/ });

    expect(tallest.style.height).toBe("100%");
    // 66.0 / 132.0 = 50%
    expect(half.style.height).toBe("50%");
  });

  test("마커가 덮는 시각에만 표시를 그린다", () => {
    const { container } = render(
      <PriceBarChart
        columns={COLUMNS}
        markers={[{ hours: [18, 19], tone: "muted", label: "지금 바로" }]}
      />,
    );
    // 마커 줄은 컬럼 수만큼 칸을 만들고, 덮는 시각에만 막대를 넣는다.
    expect(container.querySelectorAll(".bg-ink-3\\/45")).toHaveLength(2);
  });

  test("마커가 없으면 마커 줄을 만들지 않는다", () => {
    const { container } = render(<PriceBarChart columns={COLUMNS} />);
    expect(container.querySelectorAll(".bg-ink")).toHaveLength(0);
  });

  test("눈금은 지정한 간격마다 찍는다", () => {
    render(<PriceBarChart columns={COLUMNS} labelEvery={2} />);
    // 인덱스 0, 2, 4 → 18, 20, 22
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
    expect(screen.queryByText("19")).not.toBeInTheDocument();
  });

  test("막대에 초점을 주면 값이 뜬다", async () => {
    const { container } = render(<PriceBarChart columns={COLUMNS} />);
    expect(container.querySelector("[data-chart-tooltip]")).toBeNull();

    await userEvent.tab();

    const tooltip = container.querySelector("[data-chart-tooltip]");
    expect(tooltip).not.toBeNull();
    expect(tooltip).toHaveTextContent("18시");
    expect(tooltip).toHaveTextContent("최대");
    expect(tooltip).toHaveTextContent("132.0");
  });

  test("컬럼이 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<PriceBarChart columns={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("BandLegend", () => {
  test("넘긴 부하구간만 보여준다", () => {
    render(<BandLegend keys={["light", "discounted"]} />);
    expect(screen.getByText("경부하")).toBeInTheDocument();
    expect(screen.getByText("주말 할인")).toBeInTheDocument();
    expect(screen.queryByText("최대")).not.toBeInTheDocument();
  });

  test("마커 범례도 함께 보여준다", () => {
    render(<BandLegend keys={["light"]} markers={[{ label: "추천", tone: "ink" }]} />);
    expect(screen.getByText("추천")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import type { HourPrice, TimelineResponse } from "@/lib/api/types";

import Home from "./page";

const fetchTimeline = vi.fn<(params: { day: string; mode?: string }) => Promise<TimelineResponse>>();

vi.mock("@/lib/api/endpoints", () => ({
  fetchTimeline: (params: { day: string; mode?: string }) => fetchTimeline(params),
}));

/** 겨울 평일 자가 저압과 같은 모양: 22–08시 경부하, 09–12·16–19시 최대, 나머지 중간 */
function winterWeekday(): TimelineResponse {
  const hours: HourPrice[] = Array.from({ length: 24 }, (_, hour) => {
    if (hour >= 22 || hour < 8) return { hour, band: "light", discounted: false, price_per_kwh: 138 };
    if ((hour >= 9 && hour < 12) || (hour >= 16 && hour < 19))
      return { hour, band: "peak", discounted: false, price_per_kwh: 263.2 };
    return { hour, band: "middle", discounted: false, price_per_kwh: 192 };
  });
  return { day: "2026-11-04", mode: "self_low", season: "winter", is_holiday: false, hours };
}

describe("홈", () => {
  beforeEach(() => {
    fetchTimeline.mockReset();
    fetchTimeline.mockResolvedValue(winterWeekday());
  });

  test("서비스가 무엇을 해주는지 제목으로 밝힌다", () => {
    render(<Home />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "언제 충전하면 가장 쌀까요?",
    );
  });

  test("주 행동은 추천 화면으로 간다", () => {
    render(<Home />);

    expect(screen.getByRole("link", { name: "충전 시간 추천받기" })).toHaveAttribute(
      "href",
      "/recommend",
    );
  });

  /**
   * 홈은 추천 금액을 지어내지 않는다. 대신 조건 없이도 참인 오늘의 시간대별 단가를
   * 실제 응답으로 보여준다 — 기준(자가 저압)과 함께.
   */
  test("오늘 요금 판은 실제 단가 응답으로 그린다", async () => {
    render(<Home />);

    expect(await screen.findByText("22시–08시")).toBeInTheDocument();
    expect(screen.getByText("09시–12시, 16시–19시")).toBeInTheDocument();
    expect(screen.getByText("138.0원/kWh")).toBeInTheDocument();
    expect(screen.getByText("263.2원/kWh")).toBeInTheDocument();
    expect(screen.getByText(/자가 저압 기준/)).toBeInTheDocument();
    expect(fetchTimeline).toHaveBeenCalledWith(expect.objectContaining({ mode: "self_low" }));
  });

  test("단가를 못 받으면 숫자를 지어내지 않고 실패를 알린다", async () => {
    fetchTimeline.mockRejectedValue(new Error("down"));
    render(<Home />);

    expect(await screen.findByText("오늘 요금을 불러오지 못했어요")).toBeInTheDocument();
    expect(screen.queryByText(/원\/kWh/)).not.toBeInTheDocument();
  });

  test("추천·질문·단가·충전소 화면으로 가는 타일이 있다", () => {
    render(<Home />);

    const nav = screen.getByRole("navigation", { name: "바로가기" });
    const hrefs = [...nav.querySelectorAll("a")].map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(["/recommend", "/ask", "/timeline", "/stations"]);
  });

  test("요금·충전소 정보의 출처를 밝힌다", () => {
    render(<Home />);

    expect(screen.getByText(/기후에너지환경부/)).toBeInTheDocument();
    expect(screen.getByText(/한국환경공단/)).toBeInTheDocument();
  });
});

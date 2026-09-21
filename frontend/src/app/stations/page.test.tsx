import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import StationsPage from "./page";

describe("주변 충전소", () => {
  test("제목과 지도 자리, 준비 중 안내를 보여준다", () => {
    render(<StationsPage />);

    expect(screen.getByRole("heading", { level: 1, name: "주변 충전소" })).toBeInTheDocument();
    expect(screen.getByText("지도 영역")).toBeInTheDocument();
    expect(screen.getByText("준비 중")).toBeInTheDocument();
    expect(screen.getByText(/한국환경공단/)).toBeInTheDocument();
  });

  /** 가짜 충전소를 그려 두면 시연에서 "이거 실제 데이터인가요" 한마디에 무너진다. */
  test("없는 충전소 목록을 지어내지 않는다", () => {
    render(<StationsPage />);

    expect(screen.queryByText(/충전소 이름/)).not.toBeInTheDocument();
    expect(screen.queryByText("사용 가능")).not.toBeInTheDocument();
  });
});

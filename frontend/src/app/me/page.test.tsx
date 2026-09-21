import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import MePage from "./page";

describe("내 정보", () => {
  test("제목과 준비 중 안내, 돌아갈 링크를 보여준다", () => {
    render(<MePage />);

    expect(screen.getByRole("heading", { level: 1, name: "내 정보" })).toBeInTheDocument();
    expect(screen.getByText("준비 중")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "홈으로" })).toHaveAttribute("href", "/");
  });

  test("저장된 차량이나 절감액을 지어내지 않는다", () => {
    render(<MePage />);

    expect(screen.queryByText(/닉네임/)).not.toBeInTheDocument();
    expect(screen.queryByText(/kWh/)).not.toBeInTheDocument();
  });
});

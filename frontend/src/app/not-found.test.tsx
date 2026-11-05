import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import NotFound from "./not-found";

describe("404", () => {
  test("한국어로 알리고 갈 곳 두 개를 준다", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { level: 1, name: "페이지를 찾을 수 없어요" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "충전 시간 추천받기" })).toHaveAttribute("href", "/recommend");
    expect(screen.getByRole("link", { name: "홈으로" })).toHaveAttribute("href", "/");
    expect(screen.queryByText(/could not be found/i)).not.toBeInTheDocument();
  });
});

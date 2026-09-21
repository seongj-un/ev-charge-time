import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import LoginPage from "./page";

describe("로그인", () => {
  test("제목과 준비 중 안내를 보여준다", () => {
    render(<LoginPage />);

    expect(screen.getByRole("heading", { level: 1, name: "로그인" })).toBeInTheDocument();
    expect(screen.getByText("준비 중")).toBeInTheDocument();
  });

  /** 누르면 아무 일도 안 하는 입력 폼은 준비 중 안내보다 나쁘다. */
  test("동작하지 않는 로그인 폼을 그리지 않는다", () => {
    const { container } = render(<LoginPage />);

    expect(container.querySelector("form")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
  });

  test("로그인 없이 바로 쓸 수 있는 화면으로 보낸다", () => {
    render(<LoginPage />);

    expect(screen.getByRole("link", { name: "충전 시간 추천받기" })).toHaveAttribute(
      "href",
      "/recommend",
    );
  });
});

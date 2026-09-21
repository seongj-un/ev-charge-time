import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import SignupPage from "./page";

describe("회원가입", () => {
  test("제목과 준비 중 안내를 보여준다", () => {
    render(<SignupPage />);

    expect(screen.getByRole("heading", { level: 1, name: "회원가입" })).toBeInTheDocument();
    expect(screen.getByText("준비 중")).toBeInTheDocument();
  });

  test("동작하지 않는 가입 폼을 그리지 않는다", () => {
    const { container } = render(<SignupPage />);

    expect(container.querySelector("form")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
  });

  test("가입 없이 쓸 수 있는 화면으로 보낸다", () => {
    render(<SignupPage />);

    expect(screen.getByRole("link", { name: "충전 시간 추천받기" })).toHaveAttribute(
      "href",
      "/recommend",
    );
  });
});

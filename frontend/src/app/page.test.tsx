import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import Home from "./page";

describe("홈", () => {
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

  /** 홈 카드의 숫자는 계산 결과가 아니다 — 화면에서 예시라고 읽혀야 한다. */
  test("추천 카드는 예시임을 화면에 적는다", () => {
    render(<Home />);

    expect(screen.getByText(/추천 충전 시간 · 예시/)).toBeInTheDocument();
    expect(screen.getByText("22:00 – 01:00")).toBeInTheDocument();
  });

  test("단가·충전소 화면으로 가는 링크가 있다", () => {
    render(<Home />);

    expect(screen.getByRole("link", { name: /하루 단가/ })).toHaveAttribute("href", "/timeline");
    expect(screen.getByRole("link", { name: /주변 충전소/ })).toHaveAttribute("href", "/stations");
  });

  test("요금·충전소 정보의 출처를 밝힌다", () => {
    render(<Home />);

    expect(screen.getByText(/기후에너지환경부/)).toBeInTheDocument();
    expect(screen.getByText(/한국환경공단/)).toBeInTheDocument();
  });
});

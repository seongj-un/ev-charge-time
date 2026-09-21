import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { ComingSoon } from "./ComingSoon";

describe("ComingSoon", () => {
  test("화면 이름과 준비 중 표시, 못 여는 이유를 함께 보여준다", () => {
    render(<ComingSoon title="주변 충전소" reason="공단 충전소 API 연동 후 열립니다." />);

    expect(screen.getByRole("heading", { level: 1, name: "주변 충전소" })).toBeInTheDocument();
    expect(screen.getByText("준비 중")).toBeInTheDocument();
    expect(screen.getByText("공단 충전소 API 연동 후 열립니다.")).toBeInTheDocument();
  });

  test("지금 동작하는 화면으로 돌아가는 길을 준다", () => {
    render(<ComingSoon title="내 정보" reason="인증 API 연동 후 열립니다." />);

    expect(screen.getByRole("link", { name: "충전 시간 추천받기" })).toHaveAttribute(
      "href",
      "/recommend",
    );
    expect(screen.getByRole("link", { name: "하루 단가 보기" })).toHaveAttribute(
      "href",
      "/timeline",
    );
    expect(screen.getByRole("link", { name: "홈으로" })).toHaveAttribute("href", "/");
  });

  test("화면별 자리표시자를 children으로 받는다", () => {
    render(
      <ComingSoon title="주변 충전소" reason="공단 충전소 API 연동 후 열립니다.">
        <div>지도 영역</div>
      </ComingSoon>,
    );

    expect(screen.getByText("지도 영역")).toBeInTheDocument();
  });
});

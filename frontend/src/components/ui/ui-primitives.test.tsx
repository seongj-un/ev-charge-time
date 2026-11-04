import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { Button, buttonClass } from "./Button";
import { Field } from "./Field";
import { SegmentedControl } from "./SegmentedControl";

describe("Button 크기·모양", () => {
  test("lg는 필드와 같은 48px, md는 44px 터치 영역이다", () => {
    expect(buttonClass("primary", "lg")).toContain("h-12");
    expect(buttonClass("primary", "md")).toContain("h-11");
  });

  test("주 버튼은 브랜드색에서 한 단계 어두운 브랜드색으로 호버하고 알약이 아니다", () => {
    const className = buttonClass("primary");
    expect(className).toContain("bg-brand");
    expect(className).toContain("hover:bg-brand-hover");
    expect(className).toContain("rounded-field");
    expect(className).not.toContain("rounded-pill");
  });

  test("disabled가 그대로 전달된다", () => {
    render(<Button disabled>저장</Button>);
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  /*
   * pointer-events-none이 있으면 disabled:cursor-not-allowed가 보이지 않는다(죽은 스타일).
   * 클릭 차단은 네이티브 disabled가 맡는다. 클래스 문자열 검사라 실제 커서는 브라우저 QA로 본다.
   */
  test("disabled 버튼은 커서 스타일이 보이고 클릭은 네이티브 disabled가 막는다", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        저장
      </Button>,
    );
    const button = screen.getByRole("button", { name: "저장" });

    expect(button.className).toContain("disabled:cursor-not-allowed");
    expect(button.className).not.toContain("pointer-events-none");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  test("호버·눌림 색은 비활성 버튼에는 적용되지 않는다", () => {
    for (const variant of ["primary", "dark", "outline", "ghost"] as const) {
      const className = buttonClass(variant);
      expect(className).toMatch(/not-disabled:hover:/);
      expect(className).not.toMatch(/(^|\s)(hover|active):/);
    }
  });
});

describe("Field 도움말·오류", () => {
  test("도움말은 입력의 설명으로 연결되고 낮은 대비 색을 쓰지 않는다", () => {
    render(<Field label="배터리 용량" suffix="kWh" hint="차량 설명서에 적힌 값" />);

    const input = screen.getByLabelText("배터리 용량");
    expect(input).toHaveAccessibleDescription("차량 설명서에 적힌 값");
    expect(screen.getByText("차량 설명서에 적힌 값").className).toContain("text-ink-2");
    expect(screen.getByText("차량 설명서에 적힌 값").className).not.toContain("text-ink-3");
  });

  test("오류는 aria-invalid와 설명으로 연결된다", () => {
    render(<Field label="비밀번호" error="8자 이상 입력해 주세요" />);

    const input = screen.getByLabelText("비밀번호");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("8자 이상 입력해 주세요");
  });
});

describe("SegmentedControl", () => {
  test("선택값은 라디오 상태로 읽히고 각 칸은 44px 이상이다", () => {
    render(
      <SegmentedControl
        name="mode"
        label="충전 방식"
        value="a"
        options={[
          { value: "a", label: "가" },
          { value: "b", label: "나" },
        ]}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("radio", { name: "가" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "나" })).not.toBeChecked();
    expect(screen.getByText("나").closest("label")?.className).toContain("min-h-11");
  });
});

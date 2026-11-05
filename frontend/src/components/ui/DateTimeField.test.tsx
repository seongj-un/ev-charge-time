import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, test } from "vitest";

import { DateTimeField } from "./DateTimeField";

function Harness({
  initial,
  today = "2026-11-05",
  minDay,
}: {
  initial: string;
  today?: string;
  minDay?: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <DateTimeField label="충전 시작 가능" value={value} onChange={setValue} today={today} minDay={minDay} />
  );
}

const group = () => screen.getByRole("group", { name: "충전 시작 가능" });
const trigger = () => screen.getByRole("button", { name: /^충전 시작 가능 날짜/ });

describe("DateTimeField", () => {
  test("값을 잘리지 않는 한국어 날짜와 24시간 시각으로 보여준다", () => {
    render(<Harness initial="2026-11-05T20:30" />);
    expect(trigger()).toHaveTextContent("11월 5일 (목)");
    expect(trigger()).toHaveTextContent("오늘");
    expect(screen.getByRole("combobox", { name: "충전 시작 가능 시각" })).toHaveValue("20:30");
  });

  test("달력에서 날을 누르면 시각은 그대로 두고 날짜만 바뀌고, 달력이 닫히며 초점이 돌아온다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);

    await user.click(trigger());
    const dialog = screen.getByRole("dialog", { name: "충전 시작 가능 날짜 고르기" });
    await user.click(within(dialog).getByRole("button", { name: /11월 13일 / }));

    expect(group()).toHaveAttribute("data-value", "2026-11-13T20:30");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  test("시각을 고르면 날짜는 그대로다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);
    await user.selectOptions(screen.getByRole("combobox", { name: "충전 시작 가능 시각" }), "07:00");
    expect(group()).toHaveAttribute("data-value", "2026-11-05T07:00");
  });

  test("'내일' 바로가기", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);
    await user.click(trigger());
    await user.click(screen.getByRole("button", { name: "내일" }));
    expect(group()).toHaveAttribute("data-value", "2026-11-06T20:30");
  });

  test("화살표로 날을 옮기고 Enter로 고른다. 달 경계를 넘는다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-30T08:00" />);
    await user.click(trigger());
    // 열리면 고른 날에 초점이 있다
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: /11월 30일 / })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog")).toHaveAttribute("data-month", "2026-12");
    await user.keyboard("{Enter}");
    expect(group()).toHaveAttribute("data-value", "2026-12-01T08:00");
  });

  test("Esc로 닫고 날짜 버튼으로 돌아온다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);
    await user.click(trigger());
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  test("공휴일 목록이 있는 2026–2027년 밖으로는 넘기지 못한다", () => {
    render(<Harness initial="2027-12-10T08:00" />);
    fireEvent.click(trigger());
    expect(screen.getByRole("button", { name: "다음 달" })).toBeDisabled();
  });

  test("30분 간격에 안 맞는 시각도 선택지에 남아 값이 사라지지 않는다", () => {
    render(<Harness initial="2026-11-05T21:37" />);
    expect(screen.getByRole("combobox", { name: "충전 시작 가능 시각" })).toHaveValue("21:37");
  });

  test("아직 값이 없으면 시각을 고를 수 없다", () => {
    render(<Harness initial="" />);
    expect(screen.getByRole("combobox", { name: "충전 시작 가능 시각" })).toBeDisabled();
  });

  test("달력이 열린 채 Tab으로 밖에 나가면 닫힌다 — 아래 칸과 제출 버튼을 가리지 않게", async () => {
    const user = userEvent.setup();
    render(
      <>
        <Harness initial="2026-11-05T20:30" />
        <button type="button">다음 칸</button>
      </>,
    );
    await user.click(trigger());
    // 날짜 → 오늘 → 내일 → 닫기 → 바깥
    for (let i = 0; i < 4; i += 1) await user.tab();
    expect(screen.getByRole("button", { name: "다음 칸" })).toHaveFocus();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("Shift+Tab으로 달력 앞(시각 칸)으로 나가도 닫힌다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);
    await user.click(trigger());
    // 날짜 → 다음 달 → 이전 달 → 시각 칸
    for (let i = 0; i < 3; i += 1) await user.tab({ shift: true });
    expect(screen.getByRole("combobox", { name: "충전 시작 가능 시각" })).toHaveFocus();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("달력 안에서 초점이 움직이거나 달을 넘겨도 열려 있다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);
    await user.click(trigger());
    await user.click(screen.getByRole("button", { name: "다음 달" }));
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog")).toHaveAttribute("data-month", "2026-12");
  });

  test("올해가 아니면 날짜에 연도를 붙인다", () => {
    render(<Harness initial="2027-01-05T08:00" />);
    expect(trigger()).toHaveTextContent("2027년 1월 5일 (화)");
  });

  test("올해면 연도를 빼서 짧게 둔다", () => {
    render(<Harness initial="2026-12-24T08:00" />);
    expect(trigger()).toHaveTextContent("12월 24일 (목)");
    expect(trigger()).not.toHaveTextContent("2026년");
  });

  test("minDay 앞의 날은 눌러도 고를 수 없고, 그 달보다 앞으로는 넘기지 못한다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" minDay="2026-11-05" />);
    await user.click(trigger());
    const dialog = screen.getByRole("dialog");

    const past = within(dialog).getByRole("button", { name: /11월 4일 .*지난 날짜/ });
    expect(past).toHaveAttribute("aria-disabled", "true");
    await user.click(past);
    expect(group()).toHaveAttribute("data-value", "2026-11-05T20:30");
    expect(screen.getByRole("button", { name: "이전 달" })).toBeDisabled();
  });

  test("지난 날에서도 화살표로 지나갈 수 있고, Enter는 먹지 않는다", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-06T20:30" minDay="2026-11-06" />);
    await user.click(trigger());
    await user.keyboard("{ArrowLeft}");
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: /11월 5일 / })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(group()).toHaveAttribute("data-value", "2026-11-06T20:30");
  });

  test("오류가 있으면 날짜 버튼에 표시가 붙는다 (폼이 초점을 옮길 자리)", () => {
    render(<DateTimeField label="충전 시작 가능" value="2026-11-05T20:30" onChange={() => {}} error="틀렸어요" />);
    expect(trigger()).toHaveAttribute("data-invalid", "true");
  });

  test("열린 상태에서 날짜 버튼을 다시 누르면 닫힌다 (초점 이동에 닫혔다 다시 열리지 않는다)", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2026-11-05T20:30" />);
    await user.click(trigger());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.click(trigger());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

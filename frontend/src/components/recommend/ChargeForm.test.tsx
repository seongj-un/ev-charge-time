import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ChargeForm } from "./ChargeForm";

/*
 * 이 폼이 하는 일은 딱 두 가지다 — 조건을 눈으로 확인시켜 주고, 조건을 URL에 실어
 * 결과 화면으로 넘긴다. 그래서 테스트도 그 두 가지만 본다: 요약 줄이 입력을 따라오는지,
 * 그리고 이동할 때/안 할 때를 제대로 가리는지.
 *
 * router를 모킹하는 이유는 jsdom에 App Router가 없어서이기도 하지만, 무엇보다
 * "어떤 URL로 넘겼는가"가 이 화면의 계약이기 때문이다. 화면 전환이 아니라 그 URL을 본다.
 */
const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const SUBMIT = "최적 시간 찾기";

async function retype(user: UserEvent, label: string, value: string) {
  const input = screen.getByLabelText(label);
  await user.clear(input);
  await user.type(input, value);
}

/** datetime-local은 키 입력으로 채워지지 않는다(브라우저가 조각별로 받는다). 값을 직접 바꾼다. */
function setTime(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function setup() {
  const user = userEvent.setup();
  render(<ChargeForm />);
  return user;
}

async function submit(user: UserEvent) {
  await user.click(screen.getByRole("button", { name: SUBMIT }));
}

/** 시각이 비어 있으면 그것부터 오류가 나므로, 시각을 본다고 하지 않는 테스트는 먼저 채워 둔다. */
function fillTimes() {
  setTime("충전 시작 가능", "2026-10-07T18:00");
  setTime("이때까지 완료", "2026-10-08T08:00");
}

function pushedQuery(): URLSearchParams {
  const [path, query] = String(push.mock.calls[0][0]).split("?");
  expect(path).toBe("/recommend/result");
  return new URLSearchParams(query);
}

describe("ChargeForm", () => {
  beforeEach(() => {
    push.mockClear();
  });

  describe("필요 충전량 요약", () => {
    test("기본값(70 kWh · 7 kW · 30% → 60%)을 그대로 계산해 보여준다", () => {
      setup();
      expect(screen.getByText("21 kWh · 약 3시간")).toBeInTheDocument();
    });

    test("목표 충전량을 바꾸면 바로 갱신된다", async () => {
      const user = setup();
      await retype(user, "목표 충전량", "80");
      expect(screen.getByText("35 kWh · 약 5시간")).toBeInTheDocument();
    });

    test("충전기 출력을 바꾸면 소요 시간이 갱신된다", async () => {
      const user = setup();
      await retype(user, "충전기 출력", "3.5");
      expect(screen.getByText("21 kWh · 약 6시간")).toBeInTheDocument();
    });

    test("채울 게 없으면 '약 0분' 같은 말은 하지 않는다", async () => {
      const user = setup();
      await retype(user, "목표 충전량", "30");
      expect(screen.getByText("0 kWh")).toBeInTheDocument();
    });
  });

  describe("보낼 수 없는 조건은 서버에 묻지 않고 그 자리에서 알려준다", () => {
    test("목표 충전량이 현재보다 작으면 오류를 띄우고 이동하지 않는다", async () => {
      const user = setup();
      fillTimes();
      await retype(user, "목표 충전량", "20");
      await submit(user);

      expect(screen.getByText("목표 충전량은 현재보다 커야 해요")).toBeInTheDocument();
      expect(screen.getByLabelText("목표 충전량")).toHaveAttribute("aria-invalid", "true");
      expect(push).not.toHaveBeenCalled();
    });

    test("완료 시각이 시작 시각보다 앞서면 오류를 띄우고 이동하지 않는다", async () => {
      const user = setup();
      setTime("충전 시작 가능", "2026-10-07T18:00");
      setTime("이때까지 완료", "2026-10-07T17:00");
      await submit(user);

      expect(screen.getByText("완료 시각은 시작 시각보다 뒤여야 해요")).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    test("배터리 용량이 0이면 해당 칸에 오류가 붙는다", async () => {
      const user = setup();
      fillTimes();
      await retype(user, "배터리 용량", "0");
      await submit(user);

      expect(screen.getByText("배터리 용량을 0보다 크게 입력해 주세요")).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    test("충전기 출력이 비어 있으면 해당 칸에 오류가 붙는다", async () => {
      const user = setup();
      fillTimes();
      await user.clear(screen.getByLabelText("충전기 출력"));
      await submit(user);

      expect(screen.getByText("충전기 출력을 0보다 크게 입력해 주세요")).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    test("현재 충전량이 100이면 오류가 붙는다", async () => {
      const user = setup();
      fillTimes();
      await retype(user, "현재 충전량", "100");
      await submit(user);

      expect(screen.getByText("현재 충전량은 0 이상 100 미만이어야 해요")).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    test("목표 충전량이 100을 넘으면 오류가 붙는다", async () => {
      const user = setup();
      fillTimes();
      await retype(user, "목표 충전량", "120");
      await submit(user);

      expect(screen.getByText("목표 충전량은 100 이하여야 해요")).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    test("고치면 오류가 사라지고 이동한다", async () => {
      const user = setup();
      fillTimes();
      await retype(user, "목표 충전량", "20");
      await submit(user);
      expect(screen.getByText("목표 충전량은 현재보다 커야 해요")).toBeInTheDocument();

      await retype(user, "목표 충전량", "70");
      expect(screen.queryByText("목표 충전량은 현재보다 커야 해요")).not.toBeInTheDocument();

      await submit(user);
      expect(push).toHaveBeenCalledTimes(1);
    });
  });

  describe("조건을 URL에 실어 결과 화면으로 넘긴다", () => {
    test("입력한 값 그대로 쿼리에 담는다", async () => {
      const user = setup();
      fillTimes();
      await retype(user, "배터리 용량", "64");
      await retype(user, "충전기 출력", "11");
      await retype(user, "현재 충전량", "20");
      await retype(user, "목표 충전량", "90");
      await user.click(screen.getByRole("radio", { name: "자가 고압" }));
      await submit(user);

      const params = pushedQuery();
      expect(params.get("battery_kwh")).toBe("64");
      expect(params.get("charger_kw")).toBe("11");
      expect(params.get("soc_now")).toBe("20");
      expect(params.get("soc_target")).toBe("90");
      expect(params.get("earliest_start")).toBe("2026-10-07T18:00");
      expect(params.get("deadline")).toBe("2026-10-08T08:00");
      expect(params.get("mode")).toBe("self_high");
    });

    test("시각에 표준시를 붙이지 않는다", async () => {
      // 백엔드가 표준시 없는 입력을 KST로 읽는다. Z를 붙이면 9시간 어긋난 추천이 온다.
      const user = setup();
      fillTimes();
      await submit(user);

      const params = pushedQuery();
      expect(params.get("earliest_start")).not.toMatch(/[Z+]/);
      expect(params.get("deadline")).not.toMatch(/[Z+]/);
    });
  });

  describe("첫 렌더", () => {
    test("서버가 그린 HTML을 그대로 hydrate해도 경고가 나지 않는다", async () => {
      /*
       * 이 폼의 기본 시각은 '지금'에서 나온다. 서버 렌더 시각과 브라우저 렌더 시각은
       * 같을 수가 없으니, 첫 렌더에 그 값을 쓰면 hydration이 깨진다. 눈으로는 잘 안
       * 보이고 콘솔 경고로만 남아서, 실제로 서버 HTML을 만들어 붙여 보고 확인한다.
       */
      const html = renderToString(<ChargeForm />);
      // 서버 HTML에 시각이 박혀 있으면 안 된다 — 박히는 순간 클라이언트 값과 어긋난다.
      expect(html).not.toMatch(/value="\d{4}-\d{2}-\d{2}T/);

      const container = document.createElement("div");
      container.innerHTML = html;
      document.body.appendChild(container);

      const complaints: unknown[][] = [];
      const consoleError = vi
        .spyOn(console, "error")
        .mockImplementation((...args: unknown[]) => void complaints.push(args));

      const root = await act(async () => hydrateRoot(container, <ChargeForm />));

      consoleError.mockRestore();
      expect(complaints).toEqual([]);

      await act(async () => root.unmount());
      container.remove();
    });

    test("마운트 뒤에 시각 기본값이 채워진다", () => {
      // 서버와 클라이언트의 '지금'이 달라 hydration이 깨지므로 시각은 마운트 후에 넣는다.
      setup();
      const start = screen.getByLabelText<HTMLInputElement>("충전 시작 가능");
      expect(start.value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    });

    test("차량 선택은 아직 막혀 있고, 직접 입력하라고 알려준다", () => {
      setup();
      // 백엔드 /api/me/vehicles가 501이다. 가짜 차량 목록을 넣지 않는다.
      expect(screen.getByLabelText("내 차량")).toBeDisabled();
      expect(screen.getByText(/로그인 후 저장한 차량/)).toBeInTheDocument();
    });
  });
});

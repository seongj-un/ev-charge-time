import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";

import { fromSearchParams, type RecommendForm } from "@/lib/recommend-params";

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

/*
 * 이 파일의 날짜(2026-10-07 등)가 '지난 날짜'로 막히지 않게 오늘을 고정한다.
 * Date만 가짜로 둔다 — 타이머까지 멈추면 userEvent가 기다리다 끝나지 않는다.
 */
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-06T09:00:00+09:00"));
});
afterEach(() => {
  vi.useRealTimers();
});


async function retype(user: UserEvent, label: string, value: string) {
  const input = screen.getByLabelText(label);
  await user.clear(input);
  await user.type(input, value);
}

/**
 * 날짜·시각 칸을 사용자가 하듯 채운다: 날짜 버튼으로 달력을 열고, 달을 넘겨 그 날을
 * 누르고, 시각 목록에서 고른다.
 */
function setTime(label: string, value: string) {
  const [day, time] = value.split("T");
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${label} 날짜`) }));
  const dialog = screen.getByRole("dialog", { name: `${label} 날짜 고르기` });
  const target = day.slice(0, 7);
  for (let guard = 0; guard < 36 && dialog.getAttribute("data-month") !== target; guard += 1) {
    const forward = (dialog.getAttribute("data-month") ?? "") < target;
    fireEvent.click(within(dialog).getByRole("button", { name: forward ? "다음 달" : "이전 달" }));
  }
  const [, month, date] = day.split("-").map(Number);
  fireEvent.click(within(dialog).getByRole("button", { name: new RegExp(`${month}월 ${date}일 `) }));
  fireEvent.change(screen.getByRole("combobox", { name: `${label} 시각` }), { target: { value: time } });
}

/** 날짜·시각 칸의 현재 값 ("YYYY-MM-DDTHH:mm") */
function readTime(label: string): string {
  return screen.getByRole("group", { name: label }).getAttribute("data-value") ?? "";
}

/*
 * 이 파일은 폼 자체(요약·검증·URL)만 본다. 차량 불러오기는 세션이 필요하고
 * ChargeForm.vehicles.test.tsx가 따로 맡으므로, 여기서는 손님으로 고정해
 * 차량 요청이 아예 안 나가게 둔다.
 */
function stubAnonymous() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: "로그인이 필요합니다." }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
}

function Form() {
  return (
    <SessionProvider>
      <ChargeForm />
    </SessionProvider>
  );
}

function setup() {
  stubAnonymous();
  const user = userEvent.setup();
  render(<Form />);
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
      stubAnonymous();
      const html = renderToString(<Form />);
      // 서버 HTML에 시각이 박혀 있으면 안 된다 — 박히는 순간 클라이언트 값과 어긋난다.
      expect(html).not.toMatch(/value="\d{4}-\d{2}-\d{2}T/);

      const container = document.createElement("div");
      container.innerHTML = html;
      document.body.appendChild(container);

      const complaints: unknown[][] = [];
      const consoleError = vi
        .spyOn(console, "error")
        .mockImplementation((...args: unknown[]) => void complaints.push(args));

      const root = await act(async () => hydrateRoot(container, <Form />));

      consoleError.mockRestore();
      expect(complaints).toEqual([]);

      await act(async () => root.unmount());
      container.remove();
    });

    test("마운트 뒤에 시각 기본값이 채워진다", () => {
      // 서버와 클라이언트의 '지금'이 달라 hydration이 깨지므로 시각은 마운트 후에 넣는다.
      setup();
      expect(readTime("충전 시작 가능")).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    });

    test("손님에게는 차량 선택이 막혀 있고, 직접 입력해도 된다고 알려준다", () => {
      setup();
      // 가짜 차량 목록을 넣지 않는다. 로그인해야 실제 차량이 온다.
      expect(screen.getByLabelText("내 차량")).toBeDisabled();
      expect(screen.getByText(/로그인 없이 값을 직접 입력해도/)).toBeInTheDocument();
    });
  });
});

/*
 * 공공 급속은 충전사업자마다 단가가 달라 공식 값이 하나로 없다. 기본 설정의 백엔드는
 * 단가 없이 공공 급속을 계산하지 않는데, 예전 폼에는 단가 칸이 없어서 공공 급속을
 * 고르면 결과 화면에서 항상 실패했다.
 */
describe("공공 급속 단가", () => {
  beforeEach(() => {
    push.mockClear();
  });

  test("공공 급속을 고르면 단가 칸이 생기고, 단가가 URL에 실린다", async () => {
    const user = setup();
    fillTimes();
    expect(screen.queryByLabelText("공공 급속 단가")).toBeNull();

    await user.click(screen.getByRole("radio", { name: "공공 급속" }));
    await user.type(screen.getByLabelText("공공 급속 단가"), "350");
    await submit(user);

    expect(push).toHaveBeenCalledTimes(1);
    const url = new URL(push.mock.calls[0][0], "http://x");
    expect(url.searchParams.get("mode")).toBe("public_fast");
    expect(url.searchParams.get("public_base_price")).toBe("350");
  });

  test("공공 급속인데 단가가 비었으면 넘어가지 않고 그 칸에 알린다", async () => {
    const user = setup();
    fillTimes();

    await user.click(screen.getByRole("radio", { name: "공공 급속" }));
    await submit(user);

    expect(push).not.toHaveBeenCalled();
    expect(screen.getByText("충전기에 적힌 kWh당 요금을 입력해 주세요")).toBeInTheDocument();
  });

  test("자가 충전으로 돌아가면 단가는 URL에 싣지 않는다", async () => {
    const user = setup();
    fillTimes();

    await user.click(screen.getByRole("radio", { name: "공공 급속" }));
    await user.type(screen.getByLabelText("공공 급속 단가"), "350");
    await user.click(screen.getByRole("radio", { name: "자가 저압" }));
    await submit(user);

    const url = new URL(push.mock.calls[0][0], "http://x");
    expect(url.searchParams.has("public_base_price")).toBe(false);
  });
});

/*
 * 결과 화면의 "조건 고치기"는 조건을 URL에 달고 입력 화면으로 돌아온다. 입력 화면이
 * 그걸 읽지 않으면 방금 넣은 배터리·충전량·시각이 전부 기본값으로 돌아간다.
 */
describe("조건을 들고 돌아왔을 때", () => {
  beforeEach(() => {
    push.mockClear();
  });

  const BACK: RecommendForm = {
    batteryKwh: 77.4,
    chargerKw: 11,
    socNow: 25,
    socTarget: 90,
    earliestStart: "2026-11-02T21:30",
    deadline: "2026-11-03T07:00",
    mode: "public_fast",
    publicBasePrice: 347,
  };

  function setupWith(initialForm: RecommendForm) {
    stubAnonymous();
    const user = userEvent.setup();
    render(
      <SessionProvider>
        <ChargeForm initialForm={initialForm} />
      </SessionProvider>,
    );
    return user;
  }

  test("모든 칸을 그 조건으로 채운다", () => {
    setupWith(BACK);

    expect(screen.getByLabelText("배터리 용량")).toHaveValue("77.4");
    expect(screen.getByLabelText("충전기 출력")).toHaveValue("11");
    expect(screen.getByLabelText("현재 충전량")).toHaveValue("25");
    expect(screen.getByLabelText("목표 충전량")).toHaveValue("90");
    expect(readTime("충전 시작 가능")).toBe("2026-11-02T21:30");
    expect(readTime("이때까지 완료")).toBe("2026-11-03T07:00");
    expect(screen.getByRole("radio", { name: "공공 급속" })).toBeChecked();
    expect(screen.getByLabelText("공공 급속 단가")).toHaveValue("347");
  });

  test("그대로 다시 제출하면 같은 조건으로 넘어간다", async () => {
    const user = setupWith(BACK);

    await submit(user);

    const url = new URL(push.mock.calls[0][0], "http://x");
    expect(fromSearchParams(url.searchParams)).toEqual(BACK);
  });

  test("지난 날짜로 돌아왔으면 시작 칸에 알리고 넘어가지 않는다", async () => {
    vi.setSystemTime(new Date("2026-11-05T09:00:00+09:00"));
    const user = setupWith(BACK);

    await submit(user);

    expect(screen.getByText("지난 날짜예요. 오늘이나 그 뒤로 골라 주세요")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});

describe("서버가 거절할 조건도 폼에서 먼저 막는다", () => {
  beforeEach(() => {
    push.mockClear();
  });

  test("배터리 용량이 1,000 kWh를 넘으면 그 칸에 알린다", async () => {
    const user = setup();
    fillTimes();
    await retype(user, "배터리 용량", "1001");
    await submit(user);

    expect(screen.getByText("배터리 용량은 1,000 kWh 이하여야 해요")).toBeInTheDocument();
    // 범위 밖 값으로 시간까지 셈해 오류를 하나 더 띄우지 않는다
    expect(screen.queryByText(/이 시간 안에 다 못 채워요/)).not.toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  test("하루를 넘는 시간은 일·시간·분으로 쓴다 (서버 문구와 같은 꼴)", async () => {
    const user = setup();
    // 1000 kWh · 0% → 100%, 7 kW → 142시간 51분 = 5일 22시간 51분. 가능한 시간은 14시간.
    await retype(user, "배터리 용량", "1000");
    await retype(user, "현재 충전량", "0");
    await retype(user, "목표 충전량", "100");
    fillTimes();
    await submit(user);

    expect(
      screen.getByText("이 시간 안에 다 못 채워요. 충전에 약 5일 22시간 51분이 걸리는데 가능한 시간은 14시간이에요"),
    ).toBeInTheDocument();
  });

  test("충전기 출력이 1,000 kW를 넘으면 그 칸에 알린다", async () => {
    const user = setup();
    fillTimes();
    await retype(user, "충전기 출력", "1500");
    await submit(user);

    expect(screen.getByText("충전기 출력은 1,000 kW 이하여야 해요")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  test.each(["1e3", "0x10", "Infinity", "7,5"])("'%s'는 숫자로 읽지 않는다", async (raw) => {
    const user = setup();
    fillTimes();
    await retype(user, "배터리 용량", raw);
    await submit(user);

    expect(screen.getByText("배터리 용량을 0보다 크게 입력해 주세요")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  test("충전 시간이 모자라면 제출 전에 완료 칸에 사람 말로 알린다", async () => {
    const user = setup();
    // 70 kWh · 10% → 90% = 56 kWh, 7 kW로 8시간. 가능한 시간은 4시간.
    await retype(user, "현재 충전량", "10");
    await retype(user, "목표 충전량", "90");
    setTime("충전 시작 가능", "2026-10-07T22:00");
    setTime("이때까지 완료", "2026-10-08T02:00");
    await submit(user);

    expect(
      screen.getByText("이 시간 안에 다 못 채워요. 충전에 약 8시간이 걸리는데 가능한 시간은 4시간이에요"),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  test("시작부터 완료까지 14일을 넘기면 알린다", async () => {
    const user = setup();
    setTime("충전 시작 가능", "2026-10-07T18:00");
    setTime("이때까지 완료", "2026-10-22T18:00");
    await submit(user);

    expect(screen.getByText("시작부터 완료까지 14일 안으로 잡아 주세요")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  test("제출이 막히면 첫 번째 틀린 칸으로 초점이 간다", async () => {
    const user = setup();
    fillTimes();
    await retype(user, "목표 충전량", "20");
    await submit(user);

    expect(screen.getByLabelText("목표 충전량")).toHaveFocus();
  });

  test("날짜 칸이 틀렸으면 그 날짜 버튼으로 초점이 간다", async () => {
    const user = setup();
    setTime("충전 시작 가능", "2026-10-07T18:00");
    setTime("이때까지 완료", "2026-10-07T17:00");
    await submit(user);

    expect(screen.getByRole("button", { name: /^이때까지 완료 날짜/ })).toHaveFocus();
  });
});

describe("시작을 완료 뒤로 옮기면 완료가 따라온다", () => {
  test("원래 간격(14시간)을 그대로 두고 민다", () => {
    stubAnonymous();
    render(<Form />);
    fillTimes(); // 10-07 18:00 → 10-08 08:00 (14시간)
    // 날을 10-09로 고르는 순간(18:00) 완료가 14시간 뒤 10-10 08:00으로 밀리고,
    // 이어서 시각을 20:00으로 바꿔도 완료보다 앞이라 더 움직이지 않는다.
    setTime("충전 시작 가능", "2026-10-09T20:00");

    expect(readTime("이때까지 완료")).toBe("2026-10-10T08:00");
  });

  test("완료보다 앞이면 완료는 그대로다", () => {
    stubAnonymous();
    render(<Form />);
    fillTimes();
    setTime("충전 시작 가능", "2026-10-07T20:00");

    expect(readTime("이때까지 완료")).toBe("2026-10-08T08:00");
  });
});

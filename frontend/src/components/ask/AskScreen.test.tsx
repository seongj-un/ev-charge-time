import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import type { ChatResponse, RecommendResponse } from "@/lib/api/types";

import { AskScreen } from "./AskScreen";
import { FALLBACK_WAIT_SECONDS } from "./ask-view";

/*
 * 이 화면이 지켜야 하는 약속.
 *
 *   1. 숫자는 모델이 아니라 서버가 계산한 값을 보여준다. answer 문장에서
 *      숫자를 긁어오지 않는다 — 둘이 어긋나면 믿을 것은 recommendation이다.
 *   2. 조건이 모자라면 무엇이 모자란지 우리말로 말한다.
 *   3. 되묻기에 답하려면 이력이 이어져야 한다.
 *   4. 막힌 이유 네 가지(401·501·429·503)를 서로 다르게 말한다.
 *      특히 429에는 재시도 버튼을 주지 않는다 — 눌러봐야 또 429이고,
 *      그 호출도 무료 티어 할당량을 깎는다. 대신 풀리는 시각에 스스로 푼다.
 *   5. 키가 없을 때(501) 그럴듯한 답변을 지어내지 않는다.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/ask",
}));

const USER = {
  id: "u1",
  email: "user@example.com",
  nickname: "충전러",
  created_at: "2026-09-01T09:00:00+09:00",
};

/** 라이브 확인값(API 명세서 7-8의 예시와 같은 조건) */
const RECOMMENDATION: RecommendResponse = {
  best: {
    start: "2026-10-07T22:00:00+09:00",
    end: "2026-10-08T01:00:00+09:00",
    energy_kwh: 21,
    cost_won: 2373,
    discounted_kwh: 0,
  },
  baseline_now: {
    start: "2026-10-07T18:00:00+09:00",
    end: "2026-10-07T21:00:00+09:00",
    energy_kwh: 21,
    cost_won: 2654,
    discounted_kwh: 0,
  },
  savings_won: 281,
  candidates_checked: 45,
  assumptions: ["충전 출력 일정", "연속 충전", "기본요금 제외, kWh당 요금만 계산"],
  unverified_tariff_items: ["public_fast.base_price_per_kwh"],
};

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

type ChatRoute = (body: Record<string, unknown>) => Response | Promise<Response>;

type Calls = { chat: Record<string, unknown>[] };

function stubFetch(chat?: ChatRoute, me?: () => Response): Calls {
  const calls: Calls = { chat: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/me") return me?.() ?? json(USER);
      if (url === "/api/chat") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        calls.chat.push(body);
        return chat?.(body) ?? json(answer("답변"));
      }
      throw new Error(`예상하지 못한 요청: ${url}`);
    }),
  );
  return calls;
}

function answer(text: string, extra: Partial<ChatResponse> = {}): ChatResponse {
  return { answer: text, recommendation: null, missing_fields: [], ...extra };
}

async function ask(question: string) {
  const user = userEvent.setup();
  const box = await screen.findByRole("textbox", { name: /질문/ });
  await user.type(box, question);
  await user.click(screen.getByRole("button", { name: "질문 보내기" }));
  return user;
}

function renderScreen() {
  return render(
    <SessionProvider>
      <AskScreen />
    </SessionProvider>,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("들어가기 전", () => {
  /* 손님에게 입력창을 주면 질문을 다 쓴 뒤에야 401을 본다. 쓴 글이 날아간다. */
  test("로그인하지 않았으면 입력창 대신 로그인 안내를 준다", async () => {
    stubFetch(undefined, () => json({ detail: "로그인이 필요합니다" }, 401));
    renderScreen();

    expect(await screen.findByText(/로그인이 필요해요/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /질문/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /로그인/ })).toHaveAttribute(
      "href",
      expect.stringContaining("next=%2Fask"),
    );
  });

  /*
   * 백엔드가 꺼졌을 때 "로그인이 필요해요"가 뜨면 사용자는 로그인을 시도하고
   * 또 실패한다. 원인을 영영 모른다. 401만 손님으로 친다.
   */
  test("서버에 닿지 못한 것을 로그인 문제로 바꿔 말하지 않는다", async () => {
    stubFetch(undefined, () => new Response("Internal Server Error", { status: 500 }));
    renderScreen();

    expect(await screen.findByText(/서버에 연결하지 못했습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/로그인이 필요해요/)).not.toBeInTheDocument();
  });
});

describe("질문과 답", () => {
  test("질문을 보내고 답을 보여준다", async () => {
    const calls = stubFetch(() => json(answer("10월 7일 밤 10시부터 충전하세요.")));
    renderScreen();
    await ask("언제 충전하는 게 싸?");

    expect(await screen.findByText("10월 7일 밤 10시부터 충전하세요.")).toBeInTheDocument();
    expect(calls.chat[0].message).toBe("언제 충전하는 게 싸?");
  });

  test("보낸 질문도 화면에 남는다", async () => {
    stubFetch();
    renderScreen();
    await ask("언제 충전해?");

    const log = await screen.findByRole("log");
    expect(within(log).getByText("언제 충전해?")).toBeInTheDocument();
  });

  test("빈 질문은 보내지 않는다", async () => {
    const calls = stubFetch();
    renderScreen();
    const user = userEvent.setup();
    const box = await screen.findByRole("textbox", { name: /질문/ });
    await user.type(box, "   ");
    await user.click(screen.getByRole("button", { name: "질문 보내기" }));

    expect(calls.chat).toHaveLength(0);
  });

  test("보낸 뒤 입력창을 비운다", async () => {
    stubFetch();
    renderScreen();
    await ask("언제 충전해?");

    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /질문/ })).toHaveValue(""),
    );
  });

  /*
   * 되묻기가 F-10의 핵심이다. 이력을 안 보내면 서버는 "70kWh"를 첫 질문으로
   * 읽고 또 되묻는다 — 무한히 되묻는 화면이 된다.
   */
  test("두 번째 질문에 앞 대화를 실어 보낸다", async () => {
    const calls = stubFetch(() =>
      json(
        calls.chat.length === 1
          ? answer("배터리 용량을 알려주세요", { missing_fields: ["battery_kwh"] })
          : answer("10월 7일 밤 10시부터 충전하세요.", { recommendation: RECOMMENDATION }),
      ),
    );
    renderScreen();
    await ask("언제 충전해?");
    await screen.findByText("배터리 용량을 알려주세요");
    await ask("70kWh야");

    await waitFor(() => expect(calls.chat).toHaveLength(2));
    expect(calls.chat[1].history).toEqual([
      { role: "user", content: "언제 충전해?" },
      { role: "assistant", content: "배터리 용량을 알려주세요" },
    ]);
  });

  test("첫 질문에는 이력을 붙이지 않는다", async () => {
    const calls = stubFetch();
    renderScreen();
    await ask("언제 충전해?");

    await waitFor(() => expect(calls.chat).toHaveLength(1));
    expect(calls.chat[0].history).toBeUndefined();
  });
});

describe("되물을 항목", () => {
  test("무엇이 모자란지 우리말로 말한다", async () => {
    stubFetch(() =>
      json(
        answer("조건을 더 알려주세요", {
          missing_fields: ["battery_kwh", "soc_now", "deadline"],
        }),
      ),
    );
    renderScreen();
    await ask("언제 충전해?");

    const needed = await screen.findByRole("list", { name: /더 알려주실 것/ });
    expect(within(needed).getByText("배터리 용량")).toBeInTheDocument();
    expect(within(needed).getByText("현재 충전량")).toBeInTheDocument();
    expect(within(needed).getByText("완료 시각")).toBeInTheDocument();
    // 필드 이름이 그대로 새어 나오면 안 된다.
    expect(screen.queryByText(/battery_kwh/)).not.toBeInTheDocument();
  });

  test("되물을 때는 추천 카드를 만들지 않는다", async () => {
    stubFetch(() => json(answer("조건을 더 알려주세요", { missing_fields: ["battery_kwh"] })));
    renderScreen();
    await ask("언제 충전해?");

    await screen.findByRole("list", { name: /더 알려주실 것/ });
    expect(screen.queryByText(/절감/)).not.toBeInTheDocument();
  });
});

describe("추천 결과", () => {
  /*
   * 이 테스트가 이 화면에서 제일 중요하다.
   *
   * 모델은 숫자를 쓰지 않는다 (API 명세서 7-8). 금액·시각은 서버가 계산해
   * recommendation에 담아 보낸다. 화면이 answer 문장을 파싱하면 모델이 문장을
   * 조금만 다르게 써도 엉뚱한 숫자가 뜨고, 사용자는 그 시각에 실제로 차를 꽂는다.
   */
  test("서버가 계산한 값을 숫자로 보여준다", async () => {
    stubFetch(() =>
      json(
        answer("문장 속 숫자는 9999원입니다", {
          recommendation: RECOMMENDATION,
        }),
      ),
    );
    renderScreen();
    await ask("70kWh를 7kW로 30%에서 60%까지");

    const card = await screen.findByRole("group", { name: /추천 충전 시간/ });
    expect(within(card).getByText(/22:00/)).toBeInTheDocument();
    expect(within(card).getByText(/01:00/)).toBeInTheDocument();
    expect(within(card).getByText(/2,373원/)).toBeInTheDocument();
    expect(within(card).getByText(/281원/)).toBeInTheDocument();
    // 단위는 한 번만. formatKwh가 이미 "kWh"를 붙인다.
    expect(within(card).getByText("21 kWh")).toBeInTheDocument();
    // 문장에 섞인 숫자를 카드가 따라 쓰지 않는다.
    expect(within(card).queryByText(/9999/)).not.toBeInTheDocument();
  });

  test("계산 가정을 감추지 않는다", async () => {
    stubFetch(() => json(answer("답", { recommendation: RECOMMENDATION })));
    renderScreen();
    await ask("질문");

    const card = await screen.findByRole("group", { name: /추천 충전 시간/ });
    expect(within(card).getByText(/기본요금 제외/)).toBeInTheDocument();
  });

  /* 미확인 요금 항목이 있으면 금액이 잠정치라는 사실을 숨기지 않는다 (F-08). */
  test("미확인 요금이 있으면 그 사실을 알린다", async () => {
    stubFetch(() => json(answer("답", { recommendation: RECOMMENDATION })));
    renderScreen();
    await ask("질문");

    expect(await screen.findByText(/공식 요금표 확인 전/)).toBeInTheDocument();
  });
});

describe("막혔을 때", () => {
  /* 키가 없으면 답을 지어내지 않는다. 자리표시자 대화를 보여주지도 않는다. */
  test("키가 없으면(501) 준비 중이라고 말한다", async () => {
    stubFetch(() => json({ detail: "자연어 질의는 아직 준비되지 않았습니다." }, 501));
    renderScreen();
    await ask("언제 충전해?");

    expect(await screen.findByText(/준비되지 않았습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });

  /*
   * 429에 재시도 버튼을 주지 않는다. 눌러봐야 또 429이고, 그 호출도 무료 티어
   * 할당량을 깎는다. 대신 언제 풀리는지 적고 입력창을 잠근다.
   */
  test("호출 제한(429)은 언제 풀리는지 적고 입력창을 잠근다", async () => {
    vi.setSystemTime(new Date("2026-09-21T22:35:00+09:00"));
    stubFetch(() =>
      json({ detail: "질문 횟수 제한(60분당 20회)을 초과했습니다." }, 429, {
        "retry-after": "1725",
      }),
    );
    renderScreen();
    await ask("언제 충전해?");

    expect(await screen.findByText(/질문 횟수 제한/)).toBeInTheDocument();
    expect(screen.getByText(/부터 다시 물어볼 수 있어요/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "질문 보내기" })).toBeDisabled();
    vi.useRealTimers();
  });

  test("남은 시간을 모르면 시각을 지어내지 않는다", async () => {
    stubFetch(() => json({ detail: "질문 횟수 제한을 초과했습니다." }, 429));
    renderScreen();
    await ask("언제 충전해?");

    expect(await screen.findByText(/잠시 후 다시 물어봐 주세요/)).toBeInTheDocument();
  });

  /*
   * 잠금은 풀리는 시각까지만이다. 그 뒤에도 잠겨 있으면 사용자는 새로고침
   * 말고는 다시 물어볼 길이 없다 — 화면에 적힌 시각이 거짓말이 된다.
   */
  test("호출 제한은 Retry-After가 지나면 풀린다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let attempt = 0;
    const calls = stubFetch(() => {
      attempt += 1;
      return attempt === 1
        ? json({ detail: "질문 횟수 제한(60분당 20회)을 초과했습니다." }, 429, {
            "retry-after": "1725",
          })
        : json(answer("이번엔 됐습니다"));
    });
    renderScreen();
    await ask("언제 충전해?");
    await screen.findByText(/질문 횟수 제한/);
    const box = screen.getByRole("textbox", { name: /질문/ });

    // 1초 전까지는 잠겨 있다. 일찍 풀면 또 429다.
    await act(() => vi.advanceTimersByTimeAsync(1724_000));
    expect(box).toBeDisabled();

    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(box).toBeEnabled();
    expect(screen.queryByText(/질문 횟수 제한/)).not.toBeInTheDocument();

    // 풀린 뒤에는 정말로 다시 물어볼 수 있어야 한다.
    await ask("다시 물어볼게");
    expect(await screen.findByText("이번엔 됐습니다")).toBeInTheDocument();
    expect(calls.chat).toHaveLength(2);
    expect(box).toBeEnabled();
  });

  /*
   * 헤더가 없으면 언제 풀리는지 모른다. 그래도 영영 잠그지는 않는다 — 정해 둔
   * 만큼만 기다리고 푼다. 그 사이 다시 눌러봐야 또 429일 뿐이다.
   */
  test("남은 시간을 몰라도 잠금이 영영 가지는 않는다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubFetch(() => json({ detail: "질문 횟수 제한을 초과했습니다." }, 429));
    renderScreen();
    await ask("언제 충전해?");
    await screen.findByText(/잠시 후 다시 물어봐 주세요/);
    const box = screen.getByRole("textbox", { name: /질문/ });
    expect(box).toBeDisabled();

    await act(() => vi.advanceTimersByTimeAsync(FALLBACK_WAIT_SECONDS * 1000));
    expect(box).toBeEnabled();
  });

  /* 화면을 떠난 뒤에 잠금 해제 타이머가 돌면 사라진 컴포넌트의 상태를 건드린다. */
  test("화면을 떠나면 잠금 타이머를 치운다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubFetch(() =>
      json({ detail: "질문 횟수 제한을 초과했습니다." }, 429, { "retry-after": "1725" }),
    );
    const { unmount } = renderScreen();
    await ask("언제 충전해?");
    await screen.findByText(/질문 횟수 제한/);
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  /* 503은 모델 쪽 일시 실패다. 같은 질문을 그대로 다시 보낼 수 있다. */
  test("일시 실패(503)는 다시 시도할 수 있다", async () => {
    let attempt = 0;
    const calls = stubFetch(() => {
      attempt += 1;
      return attempt === 1
        ? json({ detail: "지금은 질문에 답할 수 없습니다." }, 503)
        : json(answer("이번엔 됐습니다"));
    });
    renderScreen();
    const user = await ask("언제 충전해?");

    await screen.findByText(/지금은 질문에 답할 수 없습니다/);
    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByText("이번엔 됐습니다")).toBeInTheDocument();
    expect(calls.chat).toHaveLength(2);
    // 다시 보낸 것도 같은 질문이어야 한다 — 사용자가 다시 타이핑할 이유가 없다.
    expect(calls.chat[1].message).toBe("언제 충전해?");
  });

  test("실패해도 보낸 질문은 화면에 남는다", async () => {
    stubFetch(() => json({ detail: "지금은 질문에 답할 수 없습니다." }, 503));
    renderScreen();
    await ask("언제 충전해?");

    const log = await screen.findByRole("log");
    expect(within(log).getByText("언제 충전해?")).toBeInTheDocument();
  });
});

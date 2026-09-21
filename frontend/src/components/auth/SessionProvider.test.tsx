import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider, useSession } from "./SessionProvider";

afterEach(() => {
  vi.restoreAllMocks();
});

const USER = {
  id: "u1",
  email: "user@example.com",
  nickname: "충전러",
  created_at: "2026-09-21T17:00:00+09:00",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function Probe() {
  const { status, user, signIn, signOut } = useSession();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="who">{user?.nickname ?? "-"}</span>
      <button onClick={() => signIn({ ...USER, nickname: "새사람" })}>들어가기</button>
      <button onClick={() => void signOut()}>나가기</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <SessionProvider>
      <Probe />
    </SessionProvider>,
  );
}

/*
 * 세션은 httpOnly 쿠키라 자바스크립트가 읽을 수 없다. "로그인했나?"를 아는
 * 유일한 방법은 GET /api/me를 불러 401인지 보는 것이다. 이 판단을 화면마다
 * 반복하면 같은 요청이 네 번 나가고, 화면마다 로딩 처리가 달라진다.
 */
describe("SessionProvider", () => {
  test("확인 중에는 로그인 여부를 단정하지 않는다", () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
    renderProbe();
    // "loading"이 별도 상태여야 한다. 초기값을 anonymous로 두면 로그인한
    // 사용자에게도 로그인 버튼이 한 번 번쩍인다.
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
  });

  test("/api/me가 사용자를 주면 로그인 상태가 된다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => json(USER)));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("who")).toHaveTextContent("충전러");
  });

  test("401이면 손님 상태가 된다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => json({ detail: "로그인이 필요합니다." }, 401)),
    );
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });

  /*
   * 백엔드가 꺼져 있을 때 손님으로 단정하면 "로그인하세요"가 뜬다.
   * 사용자는 로그인을 시도하고 또 실패한다. 원인을 영영 모른다.
   */
  test("서버에 닿지 못하면 손님으로 단정하지 않는다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unreachable"));
  });

  test("로그인에 성공하면 다시 묻지 않고 사용자를 받는다", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => json({ detail: "x" }, 401));
    vi.stubGlobal("fetch", fetchMock);
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));

    const callsBefore = fetchMock.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "들어가기" }));

    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("who")).toHaveTextContent("새사람");
    // 로그인 응답이 이미 사용자를 준다. /api/me를 또 부를 이유가 없다.
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  test("로그아웃하면 손님으로 돌아간다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) =>
        url === "/api/auth/logout" ? new Response(null, { status: 204 }) : json(USER),
      ),
    );
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await userEvent.click(screen.getByRole("button", { name: "나가기" }));

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });

  /*
   * 로그아웃 요청이 실패해도 화면은 손님으로 돌려야 한다. 서버 세션은 이미
   * 지워졌을 수도 있고, 무엇보다 사용자가 "나가기"를 눌렀는데 여전히 로그인
   * 상태로 남아 있으면 공용 PC에서 위험하다.
   */
  test("로그아웃 요청이 실패해도 손님으로 돌아간다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (url === "/api/auth/logout") throw new TypeError("fetch failed");
        return json(USER);
      }),
    );
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));

    await userEvent.click(screen.getByRole("button", { name: "나가기" }));

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });

  test("Provider 밖에서 쓰면 바로 알려준다", () => {
    // 조용히 손님으로 처리하면 "왜 로그인이 안 잡히지"를 한참 찾게 된다.
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/SessionProvider/);
  });
});

/*
 * 백엔드가 꺼지면 Next rewrite 프록시가 500을 돌려준다 — fetch는 성공한다.
 * "401만 손님"으로 판정하지 않으면 그 500이 손님으로 둔갑해서, 백엔드가 죽은
 * 화면에 "로그인이 필요해요"가 뜬다. 사용자는 로그인을 시도하고 또 실패한다.
 */
describe("손님과 연결 실패를 가르는 기준", () => {
  test("프록시가 준 500은 손님이 아니다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () => new Response("Internal Server Error", { status: 500 }),
      ),
    );
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unreachable"));
  });

  test("500 말고 다른 뜻밖의 상태도 손님으로 단정하지 않는다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response("nope", { status: 502 })),
    );
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("unreachable"));
  });

  test("401만 손님이다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => json({ detail: "로그인이 필요합니다." }, 401)),
    );
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });
});

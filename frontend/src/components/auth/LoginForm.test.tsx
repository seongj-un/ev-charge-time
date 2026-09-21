import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { LoginForm } from "./LoginForm";

/*
 * 이 폼이 지켜야 할 것은 네 가지다.
 *   1. 실패 이유를 서버보다 자세히 말하지 않는다 — 401은 한 문장으로 통일한다.
 *   2. 잠금(429)은 401과 다르게 안내한다. 잠긴 동안은 비밀번호가 맞아도 429라서,
 *      같은 문장을 보여주면 맞는 비밀번호를 계속 의심하며 다섯 번 더 두드린다.
 *   3. 성공하면 응답이 준 사용자를 세션에 넘긴다 (/api/me를 또 부르지 않는다).
 *   4. 돌아갈 곳(?next=)이 있으면 그리로 보낸다.
 *
 * 세션과 라우터는 앱 밖에서 돌지 않으니 가짜로 세운다. SessionProvider 자체는
 * 확정된 공유 계약이라 이 테스트에서 건드리지 않고 useSession만 갈아 끼운다.
 */
const { push, signIn, session, USER } = vi.hoisted(() => ({
  push: vi.fn(),
  signIn: vi.fn(),
  session: { status: "anonymous" as "loading" | "authenticated" | "anonymous" | "unreachable" },
  USER: {
    id: "u1",
    email: "driver@example.com",
    nickname: "충전러",
    created_at: "2026-09-21T17:00:00+09:00",
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/components/auth/SessionProvider", () => ({
  useSession: () => ({
    status: session.status,
    user: session.status === "authenticated" ? USER : null,
    signIn,
    signOut: vi.fn(),
    clear: vi.fn(),
  }),
}));

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** 호출마다 새 Response를 만든다 — 본문은 한 번만 읽힌다. */
function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockImplementation(async () => json(body, status));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  session.status = "anonymous";
  push.mockClear();
  signIn.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function fill(
  user: UserEvent,
  { email = "driver@example.com", password = "password123" } = {},
) {
  if (email) await user.type(screen.getByLabelText("이메일"), email);
  if (password) await user.type(screen.getByLabelText("비밀번호"), password);
}

function submitButton() {
  return screen.getByRole("button", { name: /로그인/ });
}

describe("LoginForm", () => {
  test("성공하면 응답이 준 사용자를 세션에 넘기고 마이페이지로 보낸다", async () => {
    const fetchMock = respondWith(USER);
    const user = userEvent.setup();
    render(<LoginForm />);

    await fill(user);
    await user.click(submitButton());

    await waitFor(() => expect(signIn).toHaveBeenCalledWith(USER));
    expect(push).toHaveBeenCalledWith("/me");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(JSON.parse(init.body)).toEqual({
      email: "driver@example.com",
      password: "password123",
    });
    // 로그인 응답이 이미 사용자를 준다. /api/me를 또 부를 이유가 없다.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  /** 추천 결과에서 "로그인하고 저장"을 누르고 온 사람은 결과로 돌아가야 한다. */
  test("돌아갈 곳이 있으면 마이페이지 대신 그리로 보낸다", async () => {
    respondWith(USER);
    const user = userEvent.setup();
    render(<LoginForm nextPath="/recommend/result?mode=self_low" />);

    await fill(user);
    await user.click(submitButton());

    await waitFor(() => expect(push).toHaveBeenCalledWith("/recommend/result?mode=self_low"));
  });

  test("엔터로 제출된다", async () => {
    const fetchMock = respondWith(USER);
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.type(screen.getByLabelText("이메일"), "driver@example.com");
    await user.type(screen.getByLabelText("비밀번호"), "password123{Enter}");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  test("401이면 어느 쪽이 틀렸는지 말하지 않고 한 문장만 보여준다", async () => {
    respondWith({ detail: "이메일 또는 비밀번호가 올바르지 않습니다" }, 401);
    const user = userEvent.setup();
    render(<LoginForm />);

    await fill(user);
    await user.click(submitButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("이메일 또는 비밀번호가 올바르지 않습니다");
    // 백엔드가 구분해 주지 않는다 — 구분하는 척하면 가입 여부가 드러난다.
    expect(alert).not.toHaveTextContent(/가입되지 않은|없는 이메일|비밀번호가 틀렸/);
    expect(signIn).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
    // 다시 시도할 수 있어야 한다.
    expect(submitButton()).toBeEnabled();
  });

  test("429 잠금은 401과 다르게 안내한다", async () => {
    respondWith({ detail: "로그인 시도가 너무 많습니다." }, 429);
    const user = userEvent.setup();
    render(<LoginForm />);

    await fill(user);
    await user.click(submitButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("15분");
    expect(alert).not.toHaveTextContent("이메일 또는 비밀번호가 올바르지 않습니다");
  });

  test("422는 서버가 준 문장을 그대로 보여준다", async () => {
    respondWith({ detail: [{ loc: ["body", "email"], msg: "이메일 형식이 아닙니다" }] }, 422);
    const user = userEvent.setup();
    render(<LoginForm />);

    await fill(user);
    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("이메일 형식이 아닙니다");
  });

  /** 429 잠금이 다섯 번 만에 걸린다. 연타로 시도 횟수를 스스로 까먹으면 안 된다. */
  test("제출 중에는 두 번째 제출을 받지 않는다", async () => {
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LoginForm />);

    await fill(user);
    await user.click(submitButton());

    await waitFor(() => expect(submitButton()).toBeDisabled());
    expect(submitButton()).toHaveTextContent("로그인 중");

    await user.click(submitButton());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("빈 칸은 서버에 보내지 않고 그 자리에 알려준다", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LoginForm />);

    await user.click(submitButton());

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("이메일")).toBeInvalid();
    expect(screen.getByLabelText("비밀번호")).toBeInvalid();
  });

  test("이미 로그인했으면 폼 대신 마이페이지로 안내한다", () => {
    session.status = "authenticated";
    render(<LoginForm />);

    // 로그인한 사람에게 로그인 폼을 또 보여주면 "로그인이 안 됐나?" 싶어진다.
    expect(screen.queryByLabelText("이메일")).toBeNull();
    expect(screen.getByText("이미 로그인했어요")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /마이페이지/ })).toHaveAttribute("href", "/me");
  });

  test("서버에 닿지 못하면 제출을 막고 이유를 알린다", () => {
    session.status = "unreachable";
    render(<LoginForm />);

    expect(screen.getByRole("alert")).toHaveTextContent("서버에 연결하지 못했습니다");
    expect(submitButton()).toBeDisabled();
  });

  test("입력은 브라우저 자동완성이 알아볼 수 있게 표시한다", () => {
    render(<LoginForm />);

    const email = screen.getByLabelText("이메일");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");

    const password = screen.getByLabelText("비밀번호");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  test("로그인 없이도 쓸 수 있는 길을 남긴다", () => {
    render(<LoginForm />);

    expect(screen.getByRole("link", { name: "로그인 없이 추천받기" })).toHaveAttribute(
      "href",
      "/recommend",
    );
    expect(screen.getByRole("link", { name: "회원가입" })).toHaveAttribute("href", "/signup");
  });
});

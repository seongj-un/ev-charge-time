import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SignupForm } from "./SignupForm";

/*
 * 가입 폼이 지켜야 할 것.
 *   1. 서버에 보내기 전에 걸러낼 것은 걸러낸다. 백엔드의 422는 영어 문장
 *      ("String should have at least 8 characters")이라 그대로는 못 보여준다.
 *   2. 409(이미 가입된 이메일)는 다른 실패와 다르게 안내하고 로그인으로 보낸다.
 *   3. 가입 응답이 쿠키까지 실어 준다 — 성공 뒤에 로그인을 또 부르면 안 된다.
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

function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
  );
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
  {
    email = "driver@example.com",
    password = "password123",
    confirm = "password123",
    nickname = "",
  } = {},
) {
  if (email) await user.type(screen.getByLabelText("이메일"), email);
  if (password) await user.type(screen.getByLabelText("비밀번호"), password);
  if (confirm) await user.type(screen.getByLabelText("비밀번호 확인"), confirm);
  if (nickname) await user.type(screen.getByLabelText("닉네임 (선택)"), nickname);
}

function submitButton() {
  return screen.getByRole("button", { name: /가입/ });
}

describe("SignupForm", () => {
  test("가입에 성공하면 이미 로그인 상태이므로 그대로 마이페이지로 보낸다", async () => {
    const fetchMock = respondWith(USER, 201);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user, { nickname: "충전러" });
    await user.click(submitButton());

    await waitFor(() => expect(signIn).toHaveBeenCalledWith(USER));
    expect(push).toHaveBeenCalledWith("/me");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/signup");
    expect(JSON.parse(init.body)).toEqual({
      email: "driver@example.com",
      password: "password123",
      nickname: "충전러",
    });
    // 가입 응답이 쿠키와 사용자를 함께 준다. 로그인도, /api/me도 다시 부르지 않는다.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("닉네임을 비우면 아예 보내지 않는다", async () => {
    const fetchMock = respondWith(USER, 201);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user);
    await user.click(submitButton());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    // 빈 문자열을 보내면 서버에 빈 닉네임이 저장된다. 선택 항목은 빠진 채로 보낸다.
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty("nickname");
  });

  test("비밀번호 확인이 다르면 서버에 보내지 않는다", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user, { confirm: "password124" });
    await user.click(submitButton());

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("비밀번호 확인")).toBeInvalid();
    expect(screen.getByText(/비밀번호가 서로 다릅니다/)).toBeInTheDocument();
  });

  /** 백엔드 제한은 8자다. 422의 영어 문장을 받아 보여주는 것보다 먼저 막는 게 낫다. */
  test("비밀번호가 8자 미만이면 서버에 보내지 않는다", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user, { password: "short", confirm: "short" });
    await user.click(submitButton());

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("비밀번호")).toBeInvalid();
    // 힌트("8자 이상")와 오류 문장은 다른 문장이어야 한다 — 같으면 무엇이 잘못됐는지 안 보인다.
    expect(screen.getByText("비밀번호는 8자 이상이어야 해요.")).toBeInTheDocument();
  });

  test("이메일 형식이 아니면 서버에 보내지 않는다", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user, { email: "driver.example.com" });
    await user.click(submitButton());

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("이메일")).toBeInvalid();
  });

  test("409면 이미 가입된 이메일이라고 알리고 로그인으로 보낸다", async () => {
    respondWith({ detail: "이미 가입된 이메일입니다." }, 409);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user);
    await user.click(submitButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("이미 가입된 이메일");
    expect(screen.getByRole("link", { name: "로그인하러 가기" })).toHaveAttribute("href", "/login");
    expect(signIn).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  test("제출 중에는 두 번째 제출을 받지 않는다", async () => {
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SignupForm />);

    await fill(user);
    await user.click(submitButton());

    await waitFor(() => expect(submitButton()).toBeDisabled());
    expect(submitButton()).toHaveTextContent("가입 중");

    await user.click(submitButton());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("이미 로그인했으면 폼 대신 마이페이지로 안내한다", () => {
    session.status = "authenticated";
    render(<SignupForm />);

    expect(screen.queryByLabelText("이메일")).toBeNull();
    expect(screen.getByText("이미 로그인했어요")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /마이페이지/ })).toHaveAttribute("href", "/me");
  });

  test("서버에 닿지 못하면 제출을 막고 이유를 알린다", () => {
    session.status = "unreachable";
    render(<SignupForm />);

    expect(screen.getByRole("alert")).toHaveTextContent("서버에 연결하지 못했습니다");
    expect(submitButton()).toBeDisabled();
  });

  test("무엇을 저장하는지 폼 안에서 밝힌다", () => {
    render(<SignupForm />);

    expect(
      screen.getByText(
        "이메일과 닉네임만 저장해요. 위치는 충전소를 찾을 때만 쓰고 저장하지 않아요.",
      ),
    ).toBeInTheDocument();
  });

  test("입력은 브라우저 자동완성이 알아볼 수 있게 표시한다", () => {
    render(<SignupForm />);

    expect(screen.getByLabelText("이메일")).toHaveAttribute("autocomplete", "email");
    // 가입은 새 비밀번호다. current-password로 두면 저장된 비밀번호가 채워진다.
    expect(screen.getByLabelText("비밀번호")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("비밀번호 확인")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("비밀번호")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("비밀번호 확인")).toHaveAttribute("type", "password");
  });
});

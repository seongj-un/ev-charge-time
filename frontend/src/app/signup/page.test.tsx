import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import SignupPage from "./page";

const { push, signIn, USER } = vi.hoisted(() => ({
  push: vi.fn(),
  signIn: vi.fn(),
  USER: {
    id: "u1",
    email: "driver@example.com",
    nickname: null,
    created_at: null,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/components/auth/SessionProvider", () => ({
  useSession: () => ({
    status: "anonymous",
    user: null,
    signIn,
    signOut: vi.fn(),
    clear: vi.fn(),
  }),
}));

beforeEach(() => {
  push.mockClear();
  signIn.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("회원가입 화면", () => {
  test("자리표시자가 아니라 동작하는 폼을 보여준다", () => {
    const { container } = render(<SignupPage />);

    expect(screen.getByRole("heading", { level: 1, name: "회원가입" })).toBeInTheDocument();
    expect(container.querySelector("form")).not.toBeNull();
    expect(screen.queryByText("준비 중")).toBeNull();

    for (const label of ["이메일", "비밀번호", "비밀번호 확인", "닉네임 (선택)"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  /** 가입 응답이 쿠키를 함께 준다 — 가입한 사람을 로그인 화면으로 되돌리면 안 된다. */
  test("가입하면 곧바로 로그인된 채로 마이페이지로 간다", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify(USER), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<SignupPage />);

    await user.type(screen.getByLabelText("이메일"), "driver@example.com");
    await user.type(screen.getByLabelText("비밀번호"), "password123");
    await user.type(screen.getByLabelText("비밀번호 확인"), "password123");
    await user.click(screen.getByRole("button", { name: "가입하기" }));

    await waitFor(() => expect(signIn).toHaveBeenCalledWith(USER));
    expect(push).toHaveBeenCalledWith("/me");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/signup");
  });
});

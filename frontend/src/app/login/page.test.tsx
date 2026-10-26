import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import LoginPage from "./page";

/*
 * 이 화면의 일은 두 가지다 — 진짜 로그인 폼을 띄우는 것, 그리고 "돌아갈 곳"을
 * URL에서 받아 폼에 넘기는 것. ?next=는 주소창에서 누구나 고칠 수 있으니
 * 외부 주소를 그대로 믿으면 로그인 직후 남의 사이트로 튕겨 보내는 통로가 된다.
 */
const { push, signIn, USER } = vi.hoisted(() => ({
  push: vi.fn(),
  signIn: vi.fn(),
  USER: {
    id: "u1",
    email: "driver@example.com",
    nickname: "충전러",
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

/** page는 async 서버 컴포넌트다. 직접 await 해서 나온 트리를 렌더한다. */
async function renderPage(params: Record<string, string | string[] | undefined> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify(USER), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
  render(await LoginPage({ searchParams: Promise.resolve(params) }));
  return userEvent.setup();
}

async function login(user: Awaited<ReturnType<typeof renderPage>>) {
  await user.type(screen.getByLabelText("이메일"), "driver@example.com");
  await user.type(screen.getByLabelText("비밀번호"), "password123");
  await user.click(screen.getByRole("button", { name: "로그인" }));
}

describe("로그인 화면", () => {
  test("자리표시자가 아니라 동작하는 폼을 보여준다", async () => {
    const { container } = render(await LoginPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("heading", { level: 1, name: "로그인" })).toBeInTheDocument();
    expect(container.querySelector("form")).not.toBeNull();
    expect(screen.queryByText("준비 중")).toBeNull();
  });

  test("돌아갈 곳이 오면 로그인 뒤 그리로 보낸다", async () => {
    const user = await renderPage({ next: "/recommend/result?mode=self_low" });

    await login(user);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/recommend/result?mode=self_low"));
  });

  test("돌아갈 곳이 없으면 마이페이지로 보낸다", async () => {
    const user = await renderPage();

    await login(user);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/me"));
  });

  /** 열린 리다이렉트 방어: 앱 안의 경로가 아니면 없는 셈 친다. */
  test.each([
    ["외부 주소", "https://evil.example.com/steal"],
    ["프로토콜 상대 주소", "//evil.example.com"],
    ["상대 경로", "recommend"],
    // ?next=%2F%09%2Fattacker.example — URL 파서가 탭·줄바꿈을 지워 //attacker.example이 된다.
    ["탭이 낀 주소", "/\t/attacker.example"],
    ["줄바꿈이 낀 주소", "/\n/attacker.example"],
    ["캐리지 리턴이 낀 주소", "/\r/attacker.example"],
    ["역슬래시 주소", "/\\attacker.example"],
    ["중간에 역슬래시", "/\t\\attacker.example"],
    ["널 문자", "/me\u0000"],
  ])("%s는 돌아갈 곳으로 받지 않는다", async (_label, next) => {
    const user = await renderPage({ next });

    await login(user);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/me"));
  });

  test("로그인 없이도 쓸 수 있는 화면으로 나갈 길을 둔다", async () => {
    render(await LoginPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("link", { name: "로그인 없이 추천받기" })).toHaveAttribute(
      "href",
      "/recommend",
    );
  });
});

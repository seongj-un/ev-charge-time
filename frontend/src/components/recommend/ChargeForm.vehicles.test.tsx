import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";

import { ChargeForm } from "./ChargeForm";

/*
 * 차량을 등록해도 추천 화면이 불러오지 않으면 "내 차량"은 아무 데도 쓰이지 않는 화면이 된다.
 * 이 파일은 그 연결만 본다 — 폼 자체의 검증·요약은 ChargeForm.test.tsx가 맡는다.
 */

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

afterEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
});

const USER = { id: "u1", email: "a@b.com", nickname: "충전러", created_at: null };

const COMMUTE = {
  id: "v1",
  name: "출퇴근 차",
  battery_kwh: 77,
  charger_kw: 11,
  mode: "self_high" as const,
  is_default: true,
};

const WEEKEND = {
  id: "v2",
  name: "주말 차",
  battery_kwh: 40,
  charger_kw: 3.5,
  mode: "public_fast" as const,
  is_default: false,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** 로그인 여부와 차량 목록을 정해 놓고 폼을 띄운다. */
function setup({
  loggedIn = true,
  vehicles = [COMMUTE, WEEKEND],
}: { loggedIn?: boolean; vehicles?: unknown[] } = {}) {
  const fetchMock = vi.fn().mockImplementation(async (url: string) => {
    if (url === "/api/me") {
      return loggedIn ? json(USER) : json({ detail: "로그인이 필요합니다." }, 401);
    }
    if (url === "/api/me/vehicles") {
      return loggedIn ? json(vehicles) : json({ detail: "로그인이 필요합니다." }, 401);
    }
    throw new Error(`예상하지 못한 요청: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  const user = userEvent.setup();
  render(
    <SessionProvider>
      <ChargeForm />
    </SessionProvider>,
  );
  return { user, fetchMock };
}

const vehicleSelect = () => screen.getByLabelText("내 차량");
const battery = () => screen.getByLabelText("배터리 용량") as HTMLInputElement;
const charger = () => screen.getByLabelText("충전기 출력") as HTMLInputElement;

describe("차량 불러오기", () => {
  test("로그인했으면 저장한 차량이 목록에 뜬다", async () => {
    setup();
    await waitFor(() => expect(vehicleSelect()).toBeEnabled());

    expect(screen.getByRole("option", { name: /출퇴근 차/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /주말 차/ })).toBeInTheDocument();
    // 직접 입력하는 길은 계속 열어 둔다 — 남의 차를 빌려 충전할 수도 있다.
    expect(screen.getByRole("option", { name: "차량 정보 직접 입력" })).toBeInTheDocument();
  });

  test("기본 차량이 있으면 그 값으로 칸을 채운다", async () => {
    setup();
    await waitFor(() => expect(battery().value).toBe("77"));
    expect(charger().value).toBe("11");
    expect(screen.getByRole("radio", { name: "자가 고압" })).toBeChecked();
  });

  test("차량을 고르면 그 차의 값으로 바뀐다", async () => {
    const { user } = setup();
    await waitFor(() => expect(vehicleSelect()).toBeEnabled());

    await user.selectOptions(vehicleSelect(), "v2");

    expect(battery().value).toBe("40");
    expect(charger().value).toBe("3.5");
    expect(screen.getByRole("radio", { name: "공공 급속" })).toBeChecked();
  });

  test("직접 입력으로 되돌리면 값을 지우지 않는다", async () => {
    // 고른 차의 값에서 조금만 고쳐 쓰는 경우가 흔하다. 되돌린다고 비우면 다시 쳐야 한다.
    const { user } = setup();
    await waitFor(() => expect(battery().value).toBe("77"));

    await user.selectOptions(vehicleSelect(), "");

    expect(battery().value).toBe("77");
  });

  /*
   * 차량 목록은 마운트 뒤에 도착한다. 그 사이 사용자가 이미 값을 고쳤다면
   * 기본 차량으로 덮어쓰면 안 된다 — 방금 친 숫자가 눈앞에서 바뀐다.
   */
  test("이미 고쳐 둔 값은 기본 차량이 덮어쓰지 않는다", async () => {
    let releaseVehicles: (value: Response) => void = () => {};
    const vehiclesArrived = new Promise<Response>((resolve) => {
      releaseVehicles = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (url === "/api/me") return json(USER);
        if (url === "/api/me/vehicles") return vehiclesArrived;
        throw new Error(`예상하지 못한 요청: ${url}`);
      }),
    );

    const user = userEvent.setup();
    render(
      <SessionProvider>
        <ChargeForm />
      </SessionProvider>,
    );

    await user.clear(battery());
    await user.type(battery(), "58");

    releaseVehicles(json([COMMUTE]));
    await waitFor(() => expect(vehicleSelect()).toBeEnabled());

    expect(battery().value).toBe("58");
  });

  test("로그인하지 않았으면 차량을 부르지 않는다", async () => {
    const { fetchMock } = setup({ loggedIn: false });
    await waitFor(() => expect(vehicleSelect()).toBeDisabled());

    // 손님에게 401이 뻔한 요청을 보낼 이유가 없다.
    expect(fetchMock.mock.calls.map((call) => call[0])).not.toContain("/api/me/vehicles");
  });

  test("로그인하지 않았으면 로그인하고 돌아올 길을 알려준다", async () => {
    setup({ loggedIn: false });
    await waitFor(() => expect(vehicleSelect()).toBeDisabled());

    const link = screen.getByRole("link", { name: /로그인/ });
    expect(link).toHaveAttribute("href", expect.stringContaining("/login"));
    expect(link).toHaveAttribute("href", expect.stringContaining("next="));
  });

  test("등록한 차량이 없으면 차량을 추가하러 갈 수 있다", async () => {
    setup({ vehicles: [] });
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /차량 추가/ })).toBeInTheDocument(),
    );
  });

  /*
   * 차량을 못 불러왔다고 폼 전체를 막으면, 직접 입력으로 추천받는 길까지 닫힌다.
   * 이 화면의 본래 목적은 로그인 없이도 쓸 수 있는 것이다.
   */
  test("차량을 못 불러와도 직접 입력은 계속 된다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (url === "/api/me") return json(USER);
        if (url === "/api/me/vehicles") return json({ detail: "서버 오류" }, 500);
        throw new Error(`예상하지 못한 요청: ${url}`);
      }),
    );
    render(
      <SessionProvider>
        <ChargeForm />
      </SessionProvider>,
    );

    await waitFor(() => expect(battery()).toBeEnabled());
    expect(screen.getByRole("button", { name: "최적 시간 찾기" })).toBeEnabled();
  });
});

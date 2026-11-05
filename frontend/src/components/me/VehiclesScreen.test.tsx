import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import type { Vehicle } from "@/lib/api/types";

import { VehiclesScreen } from "./VehiclesScreen";
import {
  COMMUTE,
  USER,
  WEEKEND,
  callsTo,
  okRoutes,
  stubApi,
  type ApiCall,
  type Route,
} from "./test-api";

/*
 * 내 차량 화면의 계약은 전부 "무슨 요청을 보냈나"다.
 *
 * 특히 is_default는 서버가 다른 차량의 기본을 해제하는 부수효과를 낸다. 화면이 그걸
 * 흉내 내면(낙관적 갱신) 서버가 실제로 무엇을 했는지와 어긋날 수 있다. 그래서
 * "바꾼 뒤 목록을 다시 불러 그 결과를 그린다"를 테스트로 못 박는다.
 *
 * PATCH는 지금 full-replace다. 필드를 빼고 보내면 그 값이 날아가므로, 무엇을 바꾸든
 * 전 필드를 함께 보내는지도 본다.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: () => {}, push: () => {}, prefetch: () => {}, refresh: () => {} }),
  usePathname: () => "/me/vehicles",
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderVehicles(routes: (call: ApiCall) => Route): ApiCall[] {
  const calls = stubApi((name, value) => vi.stubGlobal(name, value), routes);
  render(
    <SessionProvider>
      <VehiclesScreen />
    </SessionProvider>,
  );
  return calls;
}

/** 차량 카드 한 장 안에서만 찾는다. 카드마다 "수정"·"삭제"가 있어 화면 전체로 찾으면 걸린다. */
function card(name: string) {
  const heading = screen.getByRole("heading", { name });
  const item = heading.closest("li");
  if (!item) throw new Error(`${name} 카드를 찾지 못했습니다`);
  return within(item);
}

async function fillForm(
  user: UserEvent,
  values: { name: string; battery: string; charger: string },
) {
  const nameField = screen.getByLabelText("별칭");
  await user.clear(nameField);
  await user.type(nameField, values.name);
  const battery = screen.getByLabelText("배터리 (kWh)");
  await user.clear(battery);
  await user.type(battery, values.battery);
  const charger = screen.getByLabelText("충전기 출력 (kW)");
  await user.clear(charger);
  await user.type(charger, values.charger);
}

/** 목록 응답을 요청 순서대로 바꿔 가며 돌려준다 — "다시 불렀나"를 눈에 보이게 한다. */
function listSequence(...pages: Vehicle[][]): (call: ApiCall) => Route {
  let index = 0;
  return (call) => {
    if (call.url === "/api/me" && call.method === "GET") return { body: USER };
    if (call.url === "/api/me/vehicles" && call.method === "GET") {
      const page = pages[Math.min(index, pages.length - 1)];
      index += 1;
      return { body: page };
    }
    if (call.method === "POST") return { status: 201, body: { ...COMMUTE, id: "new" } };
    if (call.method === "PATCH") return { body: { ...WEEKEND, is_default: true } };
    return { status: 204 };
  };
}

describe("내 차량", () => {
  test("로그인하지 않았으면 로그인 화면으로 안내한다", async () => {
    renderVehicles(() => ({ status: 401, body: { detail: "로그인이 필요합니다." } }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "로그인" })).toHaveAttribute(
      "href",
      "/login?next=%2Fme%2Fvehicles",
    );
  });

  test("요청 도중 세션이 끊기면 로그인 안내로 떨어진다", async () => {
    renderVehicles((call) => {
      if (call.url === "/api/me" && call.method === "GET") return { body: USER };
      return { status: 401, body: { detail: "로그인이 필요합니다." } };
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
  });

  test("등록한 차량을 사양과 함께 보여준다", async () => {
    renderVehicles(okRoutes());

    expect(await screen.findByRole("heading", { name: "출퇴근 차" })).toBeInTheDocument();
    expect(card("출퇴근 차").getByText("70 kWh · 7 kW · 자가 저압")).toBeInTheDocument();
    expect(card("주말 차").getByText("60 kWh · 3.5 kW · 공공 급속")).toBeInTheDocument();
  });

  test("기본 차량에만 기본 배지가 붙는다", async () => {
    renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "출퇴근 차" });

    expect(card("출퇴근 차").getByText("기본")).toBeInTheDocument();
    expect(card("주말 차").queryByText("기본")).not.toBeInTheDocument();
    // 기본이 아닌 차에만 "기본으로" 버튼이 있다.
    expect(card("주말 차").getByRole("button", { name: "기본으로" })).toBeInTheDocument();
    expect(card("출퇴근 차").queryByRole("button", { name: "기본으로" })).not.toBeInTheDocument();
  });

  test("차량이 없으면 지어내지 않고 등록을 권한다", async () => {
    renderVehicles(okRoutes({ vehicles: [] }));

    expect(await screen.findByText("아직 등록한 차량이 없어요")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "출퇴근 차" })).not.toBeInTheDocument();
  });

  test("차량을 추가하면 목록을 다시 불러온다", async () => {
    const user = userEvent.setup();
    const added: Vehicle = {
      id: "v3",
      name: "새 차",
      battery_kwh: 50,
      charger_kw: 11,
      mode: "self_low",
      is_default: false,
    };
    const calls = renderVehicles(listSequence([COMMUTE], [COMMUTE, added]));
    await screen.findByRole("heading", { name: "출퇴근 차" });

    await fillForm(user, { name: "새 차", battery: "50", charger: "11" });
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(callsTo(calls, "POST", "/api/me/vehicles")).toHaveLength(1));
    expect(callsTo(calls, "POST", "/api/me/vehicles")[0].body).toEqual({
      name: "새 차",
      battery_kwh: 50,
      charger_kw: 11,
      mode: "self_low",
      is_default: false,
    });
    // 목록은 서버에서 다시 받는다 — 응답을 화면이 흉내 내지 않는다.
    await waitFor(() => expect(callsTo(calls, "GET", "/api/me/vehicles")).toHaveLength(2));
    expect(await screen.findByRole("heading", { name: "새 차" })).toBeInTheDocument();
  });

  test("별칭이 비면 서버로 보내지 않는다", async () => {
    const user = userEvent.setup();
    const calls = renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "출퇴근 차" });

    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(callsTo(calls, "POST", "/api/me/vehicles")).toHaveLength(0);
    expect(screen.getByText("별칭을 입력해 주세요.")).toBeInTheDocument();
  });

  test("배터리가 1,000 kWh를 넘으면 서버로 보내지 않고 추천 폼과 같은 문구로 알린다", async () => {
    const user = userEvent.setup();
    const calls = renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "출퇴근 차" });

    await fillForm(user, { name: "큰 차", battery: "1200", charger: "11" });
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(callsTo(calls, "POST", "/api/me/vehicles")).toHaveLength(0);
    expect(screen.getByText("배터리 용량은 1,000 kWh 이하여야 해요.")).toBeInTheDocument();
  });

  test("'1e3' 같은 표기는 숫자로 읽지 않는다", async () => {
    const user = userEvent.setup();
    const calls = renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "출퇴근 차" });

    await fillForm(user, { name: "큰 차", battery: "1", charger: "11" });
    // type="number"라 브라우저는 "1e3"을 받아 준다. jsdom의 user.type은 'e'를 흘리므로 값을 직접 넣는다.
    fireEvent.change(screen.getByLabelText("배터리 (kWh)"), { target: { value: "1e3" } });
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(callsTo(calls, "POST", "/api/me/vehicles")).toHaveLength(0);
    expect(screen.getByText("배터리 용량을 0보다 큰 숫자로 입력해 주세요.")).toBeInTheDocument();
  });

  test("수정은 값이 채워진 폼을 열고, 전 필드를 함께 보낸다", async () => {
    const user = userEvent.setup();
    const calls = renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "주말 차" });

    await user.click(card("주말 차").getByRole("button", { name: "수정" }));

    expect(screen.getByRole("heading", { name: "차량 수정" })).toBeInTheDocument();
    expect(screen.getByLabelText("별칭")).toHaveValue("주말 차");
    expect(screen.getByLabelText("배터리 (kWh)")).toHaveValue(60);
    expect(screen.getByLabelText("충전기 출력 (kW)")).toHaveValue(3.5);
    expect(screen.getByLabelText("기본 충전 방식")).toHaveValue("public_fast");

    const nameField = screen.getByLabelText("별칭");
    await user.clear(nameField);
    await user.type(nameField, "주말 차 2");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() =>
      expect(callsTo(calls, "PATCH", "/api/me/vehicles/v2")).toHaveLength(1),
    );
    /*
     * PATCH가 full-replace라 빠진 필드는 날아간다. 별칭만 바꿔도 전 필드를 함께 보낸다.
     * (백엔드가 진짜 부분수정으로 바뀌어도 이 본문은 그대로 맞다.)
     */
    expect(callsTo(calls, "PATCH", "/api/me/vehicles/v2")[0].body).toEqual({
      name: "주말 차 2",
      battery_kwh: 60,
      charger_kw: 3.5,
      mode: "public_fast",
      is_default: false,
    });
  });

  test("기본으로 바꾸면 서버가 준 목록을 그대로 그린다", async () => {
    const user = userEvent.setup();
    /*
     * 두 번째 목록 응답을 '아무것도 안 바뀐' 상태로 둔다. 화면이 낙관적으로 배지를
     * 옮겨 놨다면 이 테스트가 깨진다 — 기본 차량은 서버만 정한다.
     */
    const calls = renderVehicles(listSequence([COMMUTE, WEEKEND], [COMMUTE, WEEKEND]));
    await screen.findByRole("heading", { name: "주말 차" });

    await user.click(card("주말 차").getByRole("button", { name: "기본으로" }));

    await waitFor(() =>
      expect(callsTo(calls, "PATCH", "/api/me/vehicles/v2")).toHaveLength(1),
    );
    expect(callsTo(calls, "PATCH", "/api/me/vehicles/v2")[0].body).toEqual({
      name: "주말 차",
      battery_kwh: 60,
      charger_kw: 3.5,
      mode: "public_fast",
      is_default: true,
    });
    await waitFor(() => expect(callsTo(calls, "GET", "/api/me/vehicles")).toHaveLength(2));
    await waitFor(() => expect(card("출퇴근 차").getByText("기본")).toBeInTheDocument());
    expect(card("주말 차").queryByText("기본")).not.toBeInTheDocument();
  });

  test("삭제는 확인 단계를 거친다", async () => {
    const user = userEvent.setup();
    const calls = renderVehicles(listSequence([COMMUTE, WEEKEND], [COMMUTE]));
    await screen.findByRole("heading", { name: "주말 차" });

    await user.click(card("주말 차").getByRole("button", { name: "삭제" }));

    // 첫 번째 "삭제"는 물어보기만 한다. 되돌릴 수 없는 일이라 한 번 더 확인한다.
    expect(callsTo(calls, "DELETE", "/api/me/vehicles/v2")).toHaveLength(0);
    expect(card("주말 차").getByText("정말 삭제할까요?")).toBeInTheDocument();

    await user.click(card("주말 차").getByRole("button", { name: "삭제할게요" }));

    await waitFor(() =>
      expect(callsTo(calls, "DELETE", "/api/me/vehicles/v2")).toHaveLength(1),
    );
    await waitFor(() => expect(callsTo(calls, "GET", "/api/me/vehicles")).toHaveLength(2));
  });

  test("삭제를 취소하면 아무 요청도 나가지 않는다", async () => {
    const user = userEvent.setup();
    const calls = renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "주말 차" });

    await user.click(card("주말 차").getByRole("button", { name: "삭제" }));
    await user.click(card("주말 차").getByRole("button", { name: "취소" }));

    expect(callsTo(calls, "DELETE", "/api/me/vehicles/v2")).toHaveLength(0);
    expect(card("주말 차").queryByText("정말 삭제할까요?")).not.toBeInTheDocument();
  });

  test("기본 차량이 1대뿐이라는 규칙을 화면에서 밝힌다", async () => {
    renderVehicles(okRoutes());
    await screen.findByRole("heading", { name: "출퇴근 차" });

    expect(
      screen.getByText(
        "기본 차량은 1대예요. 다른 차량을 기본으로 바꾸면 기존 기본은 해제돼요.",
      ),
    ).toBeInTheDocument();
  });
});

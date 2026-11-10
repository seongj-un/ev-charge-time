import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { USER, callsTo, stubApi, type ApiCall, type Route } from "@/components/me/test-api";

import { StationsScreen } from "./StationsScreen";
import { restoreGeolocation, stubGeolocation } from "./test-support";

/*
 * 브라우저가 위치를 못 줄 때의 길: 지도를 눌러 기준점을 정한다.
 *
 * 실제 지도(Leaflet)는 jsdom에서 클릭 좌표를 만들 수 없어서, 지도 자리에 "이 좌표를
 * 눌렀다"는 버튼 하나를 세운다. 여기서 보는 건 화면 쪽 약속 — 누른 좌표로 다시 찾고,
 * 고르개가 그 사실을 말하는지 — 이다.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: () => {}, push: () => {}, prefetch: () => {}, refresh: () => {} }),
  usePathname: () => "/stations",
}));

vi.mock("./StationMap", () => ({
  StationMap: ({ onPick }: { onPick?: (coords: { lat: number; lng: number }) => void }) => (
    <button type="button" onClick={() => onPick?.({ lat: 34.95, lng: 127.48 })}>
      지도 누르기
    </button>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  restoreGeolocation();
});

function routes(call: ApiCall): Route {
  if (call.url === "/api/me" && call.method === "GET") return { body: USER };
  if (call.url.split("?")[0] === "/api/chargers") return { body: [] };
  return { status: 204 };
}

function renderScreen(): ApiCall[] {
  const calls = stubApi((name, value) => vi.stubGlobal(name, value), routes);
  render(
    <SessionProvider>
      <StationsScreen />
    </SessionProvider>,
  );
  return calls;
}

describe("주변 충전소 — 지도에서 기준점 고르기", () => {
  test("위치를 못 받아도 지도를 누른 자리로 찾는다", async () => {
    const user = userEvent.setup();
    stubGeolocation({ kind: "denied" });
    const calls = renderScreen();

    await user.click(await screen.findByRole("button", { name: "지도 누르기" }));

    await waitFor(() =>
      expect(callsTo(calls, "GET", "/api/chargers").at(-1)?.url).toContain("lat=34.95"),
    );
    expect(screen.getByRole("combobox", { name: "지역" })).toHaveDisplayValue("지도에서 고른 곳");
    expect(screen.getByText("지도를 누르면 그 자리를 기준으로 찾아요.")).toBeInTheDocument();
  });

  test("위치 실패 안내가 지도 누르기를 길로 알려 준다", async () => {
    const user = userEvent.setup();
    stubGeolocation([{ kind: "denied" }, { kind: "failed" }]);
    renderScreen();

    await user.click(await screen.findByRole("button", { name: /내 위치/ }));

    expect(await screen.findByRole("status")).toHaveTextContent(/지도를 눌러/);
  });
});

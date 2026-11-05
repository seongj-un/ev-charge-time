import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { USER, callsTo, stubApi, type ApiCall, type Route } from "@/components/me/test-api";
import type { FavoriteStation } from "@/lib/api/types";

import { FavoritesScreen } from "./FavoritesScreen";
import { FAST_AVAILABLE, favorite } from "./test-support";

/*
 * 이 화면의 기본 상태는 "이름이 없는 목록"이다.
 *
 * 이름·주소·충전기는 GET /api/chargers가 채우는 공유 캐시에서 오는데 그게 아직
 * 501이라 캐시가 비어 있다. 그래서 시안(p-12·p-24)처럼 이름이 있는 카드를 그릴
 * 데이터가 없다. 여기서는 그 빈자리를 **station_id를 이름처럼 키우는 식으로 메우지
 * 않는다**는 것과, chargers의 null과 []를 다르게 표시한다는 것을 못 박는다.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: () => {}, push: () => {}, prefetch: () => {}, refresh: () => {} }),
  usePathname: () => "/me/favorites",
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

/** 목록 응답을 요청 순서대로 바꿔 돌려준다 — "다시 불렀나"가 눈에 보이게. */
function routes(
  pages: FavoriteStation[][],
  user: Route = { body: USER },
): (call: ApiCall) => Route {
  let index = 0;
  return (call) => {
    if (call.url === "/api/me" && call.method === "GET") return user;
    if (call.url === "/api/me/favorites" && call.method === "GET") {
      const page = pages[Math.min(index, pages.length - 1)];
      index += 1;
      return { body: page };
    }
    return { status: 204 };
  };
}

function renderScreen(handler: (call: ApiCall) => Route): ApiCall[] {
  const calls = stubApi((name, value) => vi.stubGlobal(name, value), handler);
  render(
    <SessionProvider>
      <FavoritesScreen />
    </SessionProvider>,
  );
  return calls;
}

/** station_id로 카드 한 장을 집는다 — 이름이 없는 게 기본이라 이름으로는 못 찾는다. */
function card(stationId: string) {
  const item = screen.getByText(stationId).closest("li");
  if (!item) throw new Error(`${stationId} 카드를 찾지 못했습니다`);
  return within(item);
}

describe("즐겨찾는 충전소 — 로그인 상태", () => {
  test("로그인하지 않았으면 로그인으로 안내한다", async () => {
    renderScreen(routes([[]], { status: 401, body: { detail: "로그인이 필요합니다." } }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "로그인" })).toHaveAttribute(
      "href",
      "/login?next=%2Fme%2Ffavorites",
    );
  });

  test("서버에 못 닿으면 손님 취급하지 않고 연결 문제라고 말한다", async () => {
    renderScreen(routes([[]], { status: 500 }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "즐겨찾는 충전소" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/백엔드가 실행 중인지/)).toBeInTheDocument();
  });

  test("요청 도중 세션이 끊기면 로그인 안내로 떨어진다", async () => {
    renderScreen((call) => {
      if (call.url === "/api/me" && call.method === "GET") return { body: USER };
      return { status: 401, body: { detail: "로그인이 필요합니다." } };
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "로그인이 필요해요" }),
    ).toBeInTheDocument();
  });
});

describe("즐겨찾는 충전소 — 이름이 없는 오늘", () => {
  test("이름 자리에 station_id를 키워 넣지 않고, 못 불러왔다고 말한다", async () => {
    renderScreen(routes([[favorite({ station_id: "ME000001" })]]));

    expect(await screen.findByText("이름을 아직 불러오지 못했어요")).toBeInTheDocument();
    // station_id는 작게, 제목이 아니라 보조 정보로만 나온다.
    expect(card("ME000001").getByText("ME000001")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /ME000001/ })).not.toBeInTheDocument();
    // 지어낸 이름이 없어야 한다.
    expect(screen.queryByText("충전소")).not.toBeInTheDocument();
  });

  test("왜 이름이 없는지 한 줄로 설명한다", async () => {
    renderScreen(routes([[favorite({ station_id: "ME000001" })]]));

    await screen.findByText("이름을 아직 불러오지 못했어요");
    expect(screen.getByText(/한국환경공단/)).toBeInTheDocument();
    expect(screen.getByText(/이름·주소가 비어 있는 곳은/)).toBeInTheDocument();
  });

  /**
   * []는 "충전기가 0대인 충전소", null은 "아직 못 불러왔다"다 (API 명세서 7-4).
   * 둘을 같은 문장으로 그리면 사용자는 없는 충전소로 차를 몰고 간다.
   */
  test("chargers가 null인 것과 빈 배열인 것을 다르게 말한다", async () => {
    renderScreen(
      routes([
        [
          favorite({ station_id: "MISS-001", chargers: null }),
          favorite({ station_id: "ZERO-002", chargers: [] }),
        ],
      ]),
    );

    await screen.findByText("MISS-001");
    expect(card("MISS-001").getByText("충전기 정보를 아직 불러오지 못했어요")).toBeInTheDocument();
    expect(card("ZERO-002").getByText("등록된 충전기가 없어요")).toBeInTheDocument();
  });

  test("갱신 시각이 없으면 없다고 적는다", async () => {
    renderScreen(routes([[favorite({ station_id: "ME000001" })]]));

    await screen.findByText("ME000001");
    expect(screen.getByText(/상태 갱신 시각 없음/)).toBeInTheDocument();
  });
});

describe("즐겨찾는 충전소 — 목록 다루기", () => {
  test("별을 누르면 DELETE를 보내고 목록을 다시 불러온다", async () => {
    const user = userEvent.setup();
    const calls = renderScreen(
      routes([[favorite({ station_id: "ME000001" })], []]),
    );

    const star = await screen.findByRole("button", { name: "충전소 ME000001 즐겨찾기" });
    expect(star).toHaveAttribute("aria-pressed", "true");

    await user.click(star);

    await waitFor(() =>
      expect(callsTo(calls, "DELETE", "/api/me/favorites/ME000001")).toHaveLength(1),
    );
    // 목록은 서버에서 다시 받는다 — 화면이 서버가 한 일을 흉내 내지 않는다.
    await waitFor(() => expect(callsTo(calls, "GET", "/api/me/favorites")).toHaveLength(2));
    expect(await screen.findByText("아직 즐겨찾는 충전소가 없어요")).toBeInTheDocument();
  });

  test("해제가 실패하면 목록에서 지우지 않고 이유를 말한다", async () => {
    const user = userEvent.setup();
    renderScreen((call) => {
      if (call.url === "/api/me" && call.method === "GET") return { body: USER };
      if (call.url === "/api/me/favorites" && call.method === "GET") {
        return { body: [favorite({ station_id: "ME000001" })] };
      }
      return { status: 500, body: { detail: "해제하지 못했습니다." } };
    });

    await user.click(await screen.findByRole("button", { name: "충전소 ME000001 즐겨찾기" }));

    expect(await screen.findByText("해제하지 못했습니다.")).toBeInTheDocument();
    expect(screen.getByText("ME000001")).toBeInTheDocument();
  });

  test("비어 있으면 충전소 찾기로 보내되, 그쪽이 아직 501이라는 것도 알려준다", async () => {
    renderScreen(routes([[]]));

    expect(await screen.findByText("아직 즐겨찾는 충전소가 없어요")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /충전소 더 찾기/ });
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link).toHaveAttribute("href", "/stations");
    // 보내놓고 막히면 더 나쁘다.
    expect(screen.getByText(/아직 열리지 않았어요/)).toBeInTheDocument();
  });

  test("캐시가 채워진 날에는 이름과 상태를 그대로 그린다", async () => {
    renderScreen(
      routes([
        [
          favorite({
            station_id: "ME000001",
            name: "서울역 공영주차장",
            address: "서울 중구 한강대로 405",
            operator: "한국전력",
            available_hours: "24시간",
            distance_m: 320,
            chargers: [FAST_AVAILABLE],
          }),
        ],
      ]),
    );

    expect(await screen.findByRole("heading", { name: "서울역 공영주차장" })).toBeInTheDocument();
    expect(screen.getByText("사용 가능")).toBeInTheDocument();
    // 오늘이 아닌 시각이라 날짜가 붙는다 (station-view statusUpdatedLabel)
    expect(screen.getByText(/상태 갱신 (\d+월 \d+일 )?22:10/)).toBeInTheDocument();
    expect(screen.queryByText("이름을 아직 불러오지 못했어요")).not.toBeInTheDocument();
    // 이름·주소가 다 있으면 "비어 있는 곳은…" 안내를 붙이지 않는다
    expect(screen.queryByText(/이름·주소가 비어 있는 곳은/)).not.toBeInTheDocument();
  });
});

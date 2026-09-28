import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { USER, callsTo, stubApi, type ApiCall, type Route } from "@/components/me/test-api";

import { AREAS, DEFAULT_AREA } from "./station-view";
import { StationsScreen } from "./StationsScreen";
import {
  FAST_AVAILABLE,
  SLOW_CHARGING,
  UNKNOWN_STATUS,
  restoreGeolocation,
  station,
  stubGeolocation,
} from "./test-support";

/*
 * 이 화면의 계약은 두 가지다.
 *
 * 1) 오늘: GET /api/chargers가 501이다. 그러면 이유를 밝히고 **목록을 만들지 않는다.**
 * 2) 데이터가 오는 날: 같은 코드가 목록·필터·즐겨찾기 토글을 그대로 해낸다.
 *
 * 둘을 같은 파일에서 본다. 501 안내만 테스트하면 연동된 날 화면이 동작하는지 아무도
 * 모르고, 목록만 테스트하면 오늘 가짜 목록이 떠도 아무도 모른다.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: () => {}, push: () => {}, prefetch: () => {}, refresh: () => {} }),
  usePathname: () => "/stations",
}));

afterEach(() => {
  vi.unstubAllGlobals();
  restoreGeolocation();
});

const SEOUL = { kind: "granted", lat: 37.5547, lng: 126.9707 } as const;

const NOT_IMPLEMENTED: Route = {
  status: 501,
  body: { detail: "주변 충전소 조회은(는) 아직 구현되지 않았습니다." },
};

/** 로그인한 사용자 + 주어진 충전소 응답 */
function routes(chargers: Route, user: Route = { body: USER }): (call: ApiCall) => Route {
  return (call) => {
    if (call.url === "/api/me" && call.method === "GET") return user;
    if (call.url.split("?")[0] === "/api/chargers") return chargers;
    return { status: 204 };
  };
}

function renderScreen(handler: (call: ApiCall) => Route): ApiCall[] {
  const calls = stubApi((name, value) => vi.stubGlobal(name, value), handler);
  render(
    <SessionProvider>
      <StationsScreen />
    </SessionProvider>,
  );
  return calls;
}

function stationItem(name: string) {
  const heading = screen.getByRole("heading", { name });
  const item = heading.closest("li");
  if (!item) throw new Error(`${name} 카드를 찾지 못했습니다`);
  return within(item);
}

describe("주변 충전소 — 백엔드가 501인 오늘", () => {
  test("왜 못 여는지 밝히고 충전소를 지어내지 않는다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes(NOT_IMPLEMENTED));

    /*
     * 각주에도 "한국환경공단"이 있어서 그걸로 기다리면 501 안내가 뜨기 전에 통과한다.
     * 501일 때만 나오는 문구를 기다려야 이 테스트가 실제로 안내를 검사한다.
     */
    expect(await screen.findByText(/연동/)).toBeInTheDocument();
    expect(screen.getAllByText(/한국환경공단/).length).toBeGreaterThan(0);

    // 목록이 아예 없어야 한다. 껍데기 카드도 안 된다.
    expect(screen.queryByRole("list", { name: "충전소 목록" })).not.toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    expect(screen.queryByText("사용 가능")).not.toBeInTheDocument();
    expect(screen.queryByText(/충전소 이름/)).not.toBeInTheDocument();
  });

  test("위치는 받아서 실제로 호출해 본다 — 501을 미리 넘겨짚지 않는다", async () => {
    stubGeolocation(SEOUL);
    const calls = renderScreen(routes(NOT_IMPLEMENTED));

    await waitFor(() => expect(callsTo(calls, "GET", "/api/chargers")).toHaveLength(1));
    expect(callsTo(calls, "GET", "/api/chargers")[0].url).toContain("lat=37.5547");
    expect(callsTo(calls, "GET", "/api/chargers")[0].url).toContain("lng=126.9707");
  });

  test("501이어도 즐겨찾기로 가는 길은 열어 둔다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes(NOT_IMPLEMENTED));

    await screen.findByText(/한국환경공단/);
    expect(screen.getByRole("link", { name: /즐겨찾기/ })).toHaveAttribute(
      "href",
      "/me/favorites",
    );
  });
});

/*
 * 위치는 이 화면에서 제일 잘 깨지는 부분이다.
 *
 * 실제로 겪은 것: 사이트 권한이 "granted"인데도 getCurrentPosition이
 * PERMISSION_DENIED로 떨어졌다. macOS가 Chrome의 위치 서비스를 막고 있으면
 * 그렇게 된다. 사용자는 브라우저에서 아무리 "허용"을 눌러도 못 고친다.
 *
 * 그래서 이 화면은 **위치를 못 얻어도 쓸 수 있어야 한다.** 막다른 길로 두면
 * 심사위원 노트북이 같은 상태일 때 그 자리에서 죽는다.
 */
describe("주변 충전소 — 위치", () => {
  test("위치를 못 얻으면 기본 지역으로라도 찾아 준다", async () => {
    stubGeolocation({ kind: "denied" });
    const calls = renderScreen(routes(NOT_IMPLEMENTED));

    await waitFor(() => expect(callsTo(calls, "GET", "/api/chargers")).toHaveLength(1));
    const url = callsTo(calls, "GET", "/api/chargers")[0].url;
    expect(url).toContain(`lat=${DEFAULT_AREA.lat}`);
    expect(url).toContain(`lng=${DEFAULT_AREA.lng}`);
  });

  test("어느 지역을 보고 있는지 밝힌다 — 내 위치인 척하지 않는다", async () => {
    stubGeolocation({ kind: "denied" });
    renderScreen(routes(NOT_IMPLEMENTED));

    expect(await screen.findByText(new RegExp(DEFAULT_AREA.name))).toBeInTheDocument();
  });

  test("지역을 바꾸면 그 좌표로 다시 찾는다", async () => {
    const user = userEvent.setup();
    stubGeolocation({ kind: "denied" });
    const calls = renderScreen(routes(NOT_IMPLEMENTED));

    const picker = await screen.findByRole("combobox", { name: /지역/ });
    const 목포 = AREAS.find((a) => a.id === "mokpo")!;
    await user.selectOptions(picker, 목포.id);

    await waitFor(() => {
      const urls = callsTo(calls, "GET", "/api/chargers").map((c) => c.url);
      expect(urls.some((u) => u.includes(`lat=${목포.lat}`))).toBe(true);
    });
  });

  test("내 위치로 다시 시도할 길을 남긴다", async () => {
    const user = userEvent.setup();
    const geo = stubGeolocation([{ kind: "denied" }, SEOUL]);
    const calls = renderScreen(routes(NOT_IMPLEMENTED));

    const retry = await screen.findByRole("button", { name: /내 위치/ });
    expect(geo.calls).toBe(1);
    await user.click(retry);

    await waitFor(() => expect(geo.calls).toBe(2));
    await waitFor(() => {
      const urls = callsTo(calls, "GET", "/api/chargers").map((c) => c.url);
      expect(urls.some((u) => u.includes(`lat=${SEOUL.lat}`))).toBe(true);
    });
  });

  /*
   * 눌렀는데 아무 일도 안 일어나는 것처럼 보이면 안 된다.
   *
   * 기본 지역을 보고 있는 상태에서 "내 위치로 찾기"가 실패하면 결과가 같은
   * 화면이다. 아무 말도 안 하면 사용자는 버튼이 고장났다고 읽는다 — 실제로
   * 그렇게 보고됐다.
   */
  test("내 위치로 찾기가 실패하면 그 사실을 말한다", async () => {
    const user = userEvent.setup();
    stubGeolocation({ kind: "denied" });
    renderScreen(routes(NOT_IMPLEMENTED));

    const button = await screen.findByRole("button", { name: /내 위치/ });
    await user.click(button);

    expect(await screen.findByRole("status")).toHaveTextContent(/위치를 얻지 못했어요/);
  });

  /* 목포를 보다가 눌렀는데 실패했다고 빛가람으로 끌려가면 안 된다. */
  test("실패해도 보던 지역을 그대로 둔다", async () => {
    const user = userEvent.setup();
    stubGeolocation({ kind: "denied" });
    const calls = renderScreen(routes(NOT_IMPLEMENTED));

    const picker = await screen.findByRole("combobox", { name: /지역/ });
    const 목포 = AREAS.find((a) => a.id === "mokpo")!;
    await user.selectOptions(picker, 목포.id);
    await waitFor(() =>
      expect(
        callsTo(calls, "GET", "/api/chargers").some((c) => c.url.includes(`lat=${목포.lat}`)),
      ).toBe(true),
    );

    await user.click(screen.getByRole("button", { name: /내 위치/ }));
    await screen.findByRole("status");

    expect(screen.getByRole("combobox", { name: /지역/ })).toHaveValue(목포.id);
  });

  test("위치를 얻으면 안내가 사라진다", async () => {
    const user = userEvent.setup();
    stubGeolocation([{ kind: "denied" }, { kind: "denied" }, SEOUL]);
    renderScreen(routes(NOT_IMPLEMENTED));

    const button = await screen.findByRole("button", { name: /내 위치/ });
    await user.click(button);
    await screen.findByRole("status");

    await user.click(screen.getByRole("button", { name: /내 위치/ }));
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });

  /*
   * 응답이 아예 안 오는 경우. timeout 옵션이 없으면 화면이 영영 로딩에 갇힌다 —
   * 에러가 오는 것보다 나쁜 실패 모드다.
   */
  test("위치 요청에 제한 시간을 건다", async () => {
    const geo = stubGeolocation({ kind: "hang" });
    renderScreen(routes(NOT_IMPLEMENTED));

    await waitFor(() => expect(geo.calls).toBe(1));
    expect(geo.options[0]?.timeout).toBeGreaterThan(0);
  });

  test("응답이 없어도 기본 지역으로 넘어간다", async () => {
    vi.useFakeTimers();
    try {
      stubGeolocation({ kind: "hang" });
      const calls = renderScreen(routes(NOT_IMPLEMENTED));
      // 제한 시간이 지나면 스스로 포기하고 기본 지역으로 간다.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000);
      });
      expect(callsTo(calls, "GET", "/api/chargers").length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });

  test("브라우저에 위치 기능이 없어도 기본 지역으로 찾아 준다", async () => {
    stubGeolocation({ kind: "missing" });
    const calls = renderScreen(routes(NOT_IMPLEMENTED));

    await waitFor(() => expect(callsTo(calls, "GET", "/api/chargers")).toHaveLength(1));
  });

  test("각주에 좌표를 저장하지 않는다는 것을 밝힌다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes(NOT_IMPLEMENTED));

    await screen.findByText(/한국환경공단/);
    expect(screen.getByText(/위치는 조회에만 쓰고 저장하지 않아요/)).toBeInTheDocument();
  });
});

describe("주변 충전소 — 데이터가 오는 날", () => {
  const 서울역 = station({
    station_id: "ME000001",
    name: "서울역 공영주차장",
    distance_m: 320,
    chargers: [FAST_AVAILABLE],
  });
  const 시청 = station({
    station_id: "ME000002",
    name: "시청 앞 충전소",
    address: "서울 중구 세종대로 110",
    operator: "환경부",
    distance_m: 1240,
    chargers: [SLOW_CHARGING],
  });
  const 남산 = station({
    station_id: "ME000003",
    name: "남산 주차장",
    distance_m: 2100,
    chargers: [UNKNOWN_STATUS],
  });

  test("이름·주소·거리·충전기를 계약대로 그린다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [서울역, 시청] }));

    expect(await screen.findByRole("heading", { name: "서울역 공영주차장" })).toBeInTheDocument();
    expect(stationItem("서울역 공영주차장").getByText("320 m")).toBeInTheDocument();
    expect(
      stationItem("서울역 공영주차장").getByText("서울 중구 한강대로 405 · 한국전력 · 24시간"),
    ).toBeInTheDocument();
    expect(stationItem("서울역 공영주차장").getByText("사용 가능")).toBeInTheDocument();
    expect(stationItem("시청 앞 충전소").getByText("1.2 km")).toBeInTheDocument();
    expect(stationItem("시청 앞 충전소").getByText("충전 중")).toBeInTheDocument();
  });

  test("모르는 상태 코드는 코드 그대로 보여준다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [남산] }));

    await screen.findByRole("heading", { name: "남산 주차장" });
    // stat=7은 공식 코드표(활용가이드 v1.25 3.2절)에 없다. 뜻을 지어내지 않고 원문을 남긴다.
    expect(stationItem("남산 주차장").getByText("7")).toBeInTheDocument();
    expect(screen.queryByText("사용 가능")).not.toBeInTheDocument();
    // 왜 코드가 그대로 보이는지 화면이 한 줄로 설명한다.
    expect(screen.getByText(/공식 코드표에 없는 상태 코드/)).toBeInTheDocument();
  });

  /*
   * 9(상태미확인)는 실데이터의 5%가 넘는다. 공식 코드라서 뜻을 붙여 보여주고,
   * "코드표에 없는 코드" 안내는 띄우지 않는다 — 띄우면 화면이 늘 그 말을 한다.
   */
  test("상태미확인(9)은 공식 코드라 뜻으로 보여준다", async () => {
    stubGeolocation(SEOUL);
    const 미확인 = station({
      station_id: "ME000009",
      name: "상태 미확인 충전소",
      chargers: [{ ...UNKNOWN_STATUS, charger_id: "c-9", status: "9" }],
    });
    renderScreen(routes({ body: [미확인] }));

    await screen.findByRole("heading", { name: "상태 미확인 충전소" });
    expect(stationItem("상태 미확인 충전소").getByText("상태 미확인")).toBeInTheDocument();
    expect(screen.queryByText(/공식 코드표에 없는 상태 코드/)).not.toBeInTheDocument();
  });

  /*
   * 타입 코드는 뜻을 모르고 속도도 정하지 못한다(type=04가 7~350 kW). 보여주면
   * 사용자가 읽어낼 것이 없는 숫자만 는다. 대신 출력으로 속도를 말한다.
   */
  test("타입 코드를 화면에 흘리지 않고 출력으로 속도를 말한다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [서울역] }));

    await screen.findByRole("heading", { name: "서울역 공영주차장" });
    expect(stationItem("서울역 공영주차장").getByText("급속")).toBeInTheDocument();
    expect(stationItem("서울역 공영주차장").getByText("100 kW")).toBeInTheDocument();
    expect(stationItem("서울역 공영주차장").queryByText("04")).not.toBeInTheDocument();
  });

  test("급속 필터는 급속이 있는 충전소만 남긴다", async () => {
    const user = userEvent.setup();
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [서울역, 시청] }));

    await screen.findByRole("heading", { name: "시청 앞 충전소" });
    await user.click(screen.getByRole("radio", { name: "급속" }));

    expect(screen.getByRole("heading", { name: "서울역 공영주차장" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "시청 앞 충전소" })).not.toBeInTheDocument();
  });

  test("사용 가능만은 확인된 코드만 남기고, 그 사실을 밝힌다", async () => {
    const user = userEvent.setup();
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [서울역, 남산] }));

    await screen.findByRole("heading", { name: "남산 주차장" });
    await user.click(screen.getByRole("checkbox", { name: "사용 가능만" }));

    expect(screen.getByRole("heading", { name: "서울역 공영주차장" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "남산 주차장" })).not.toBeInTheDocument();
    expect(screen.getByText(/확인된 코드만 남겨요/)).toBeInTheDocument();
  });

  test("필터가 전부 걸러내면 빈 화면 대신 이유를 말한다", async () => {
    const user = userEvent.setup();
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [시청] }));

    await screen.findByRole("heading", { name: "시청 앞 충전소" });
    await user.click(screen.getByRole("radio", { name: "급속" }));

    expect(screen.getByText("고른 조건에 맞는 충전소가 없어요")).toBeInTheDocument();
  });

  /*
   * "없다"와 "아직 수집하지 않았다"는 다른 말이다. 캐시가 전남·광주만 담고
   * 있어서 서울에서 열면 빈 목록이 오는데, 그걸 "주변에 없다"고 하면 거짓말이
   * 된다. 프론트는 어느 쪽인지 알 수 없으므로 둘 다 말한다.
   */
  test("빈 목록을 '충전소가 없다'로 단정하지 않는다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [] }));

    expect(await screen.findByText("이 근처에서 충전소를 찾지 못했어요")).toBeInTheDocument();
    expect(screen.getByText(/전남·광주 지역 충전소만 수집/)).toBeInTheDocument();
  });

  test("별을 누르면 즐겨찾기에 넣고, 다시 누르면 뺀다", async () => {
    const user = userEvent.setup();
    stubGeolocation(SEOUL);
    const calls = renderScreen(routes({ body: [서울역] }));

    const star = await screen.findByRole("button", { name: "서울역 공영주차장 즐겨찾기" });
    expect(star).toHaveAttribute("aria-pressed", "false");

    await user.click(star);
    await waitFor(() =>
      expect(callsTo(calls, "PUT", "/api/me/favorites/ME000001")).toHaveLength(1),
    );
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "true"));

    await user.click(star);
    await waitFor(() =>
      expect(callsTo(calls, "DELETE", "/api/me/favorites/ME000001")).toHaveLength(1),
    );
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "false"));
  });

  test("서버가 이미 즐겨찾기라고 하면 눌린 채로 시작한다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [{ ...서울역, is_favorite: true }] }));

    expect(
      await screen.findByRole("button", { name: "서울역 공영주차장 즐겨찾기" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  test("즐겨찾기 요청이 실패하면 눌린 것처럼 굴지 않는다", async () => {
    const user = userEvent.setup();
    stubGeolocation(SEOUL);
    renderScreen((call) => {
      if (call.url === "/api/me" && call.method === "GET") return { body: USER };
      if (call.url.split("?")[0] === "/api/chargers") return { body: [서울역] };
      return { status: 500, body: { detail: "저장하지 못했습니다." } };
    });

    const star = await screen.findByRole("button", { name: "서울역 공영주차장 즐겨찾기" });
    await user.click(star);

    expect(await screen.findByText("저장하지 못했습니다.")).toBeInTheDocument();
    expect(star).toHaveAttribute("aria-pressed", "false");
  });

  test("손님에게는 눌러도 안 되는 별 대신 로그인 링크를 준다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(
      routes({ body: [{ ...서울역, is_favorite: null }] }, { status: 401, body: { detail: "로그인이 필요합니다." } }),
    );

    await screen.findByRole("heading", { name: "서울역 공영주차장" });
    expect(
      screen.queryByRole("button", { name: "서울역 공영주차장 즐겨찾기" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "로그인하고 서울역 공영주차장 즐겨찾기" }),
    ).toHaveAttribute("href", "/login?next=%2Fstations");
  });

  test("각주에 상태 갱신 시각을 적는다", async () => {
    stubGeolocation(SEOUL);
    renderScreen(routes({ body: [서울역] }));

    await screen.findByRole("heading", { name: "서울역 공영주차장" });
    expect(screen.getByText(/상태 갱신 22:10/)).toBeInTheDocument();
  });
});

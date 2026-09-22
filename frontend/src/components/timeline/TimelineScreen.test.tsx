import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { HourPrice, TimelineResponse } from "@/lib/api/types";

import { TimelineScreen } from "./TimelineScreen";

/*
 * 이 화면이 하는 약속은 두 가지다.
 *   1) 응답에 있는 것만 보여준다 — 없는 할인, 없는 부하구간을 지어내지 않는다.
 *   2) 못 가져왔으면 못 가져왔다고 말한다 — 빈 차트로 얼버무리지 않는다.
 * 테스트는 그 두 가지를 지킨다.
 */

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** 디자인(p-04)과 같은 모양의 하루: 0–7 경부하, 8–10 중간, 11–13 할인, 14–21 중간, 22–23 경부하 */
function weekendHours(): HourPrice[] {
  return Array.from({ length: 24 }, (_, hour): HourPrice => {
    if (hour >= 11 && hour <= 13) {
      return { hour, band: "middle", discounted: true, price_per_kwh: 71.2 };
    }
    if (hour <= 7 || hour >= 22) {
      return { hour, band: "light", discounted: false, price_per_kwh: 113.0 };
    }
    return { hour, band: "middle", discounted: false, price_per_kwh: 126.4 };
  });
}

/** 할인이 하나도 없는 평일 */
function weekdayHours(): HourPrice[] {
  return Array.from({ length: 24 }, (_, hour): HourPrice =>
    hour <= 8
      ? { hour, band: "light", discounted: false, price_per_kwh: 113.0 }
      : { hour, band: "middle", discounted: false, price_per_kwh: 126.4 },
  );
}

function timeline(overrides: Partial<TimelineResponse> = {}): TimelineResponse {
  return {
    day: "2026-10-10",
    mode: "self_low",
    season: "spring_fall",
    is_holiday: false,
    hours: weekendHours(),
    ...overrides,
  };
}

/** fetch를 세워 두고, 호출된 URL 목록을 돌려준다. */
function stubFetch(
  respond: (url: string) => { status?: number; body: unknown },
): { urls: string[] } {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      const { status = 200, body } = respond(url);
      return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return { urls };
}

/** 차트 막대는 접근 이름이 "…원/kWh"인 버튼이다 (PriceBarChart) */
function bars() {
  return screen.getAllByRole("button", { name: /원\/kWh$/ });
}

describe("TimelineScreen", () => {
  test("응답을 받으면 24개 막대와 단가 목록이 보인다", async () => {
    stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);

    await waitFor(() => expect(bars()).toHaveLength(24));

    const priceList = await screen.findByRole("list", { name: "부하구간별 단가" });
    expect(within(priceList).getByText("경부하")).toBeInTheDocument();
    expect(within(priceList).getByText("113.0")).toBeInTheDocument();
    expect(within(priceList).getByText("중간부하")).toBeInTheDocument();
    expect(within(priceList).getByText("126.4")).toBeInTheDocument();
    expect(within(priceList).getByText("주말 할인")).toBeInTheDocument();
    expect(within(priceList).getByText("71.2")).toBeInTheDocument();

    // 최대부하가 없는 날이다. 목록에도 범례에도 나오면 안 된다.
    expect(within(priceList).queryByText("최대부하")).toBeNull();
  });

  test("각주는 언제나 붙는다 — 확인이 끝났으면 출처를 적는다", async () => {
    // 각주 자체를 빼면 화면이 숫자의 출처를 말하지 않게 된다.
    stubFetch((url) =>
      url.startsWith("/health")
        ? { body: { status: "ok", unverified_tariff_items: [] } }
        : { body: timeline() },
    );

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);

    expect(await screen.findByText(/한국전력공사 전기요금표/)).toBeInTheDocument();
  });

  test("응답의 계절·요일에서 부제를 만든다", async () => {
    stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);

    expect(await screen.findAllByText("시뮬레이션 · 봄·가을 주말")).not.toHaveLength(0);
    expect(screen.getAllByText("10월 10일 (토)").length).toBeGreaterThan(0);
  });

  test("할인이 없는 날엔 라임 배너가 뜨지 않는다", async () => {
    stubFetch(() => ({
      body: timeline({ day: "2026-10-12", is_holiday: false, hours: weekdayHours() }),
    }));

    render(<TimelineScreen initialDay="2026-10-12" initialMode="self_low" />);

    await waitFor(() => expect(bars()).toHaveLength(24));
    expect(screen.queryByText(/50% 할인/)).toBeNull();
    expect(screen.queryByText("주말 할인")).toBeNull();
  });

  test("할인이 걸린 시각이 있으면 라임 배너가 그 구간을 적는다", async () => {
    stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);

    const banner = await screen.findByRole("note", { name: "전력량요금 할인" });
    expect(within(banner).getByText(/11–14시/)).toBeInTheDocument();
    expect(within(banner).getByText(/50% 할인/)).toBeInTheDocument();
  });

  test("오류면 백엔드가 준 메시지를 그대로 보여준다", async () => {
    stubFetch(() => ({ status: 422, body: { detail: "day는 YYYY-MM-DD여야 합니다." } }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("day는 YYYY-MM-DD여야 합니다.");
    expect(screen.queryByRole("list", { name: "부하구간별 단가" })).toBeNull();
  });

  test("다음 날 버튼을 누르면 하루 뒤를 다시 부른다", async () => {
    const user = userEvent.setup();
    const { urls } = stubFetch((url) => ({
      body: timeline({ day: url.includes("2026-10-11") ? "2026-10-11" : "2026-10-10" }),
    }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
    await waitFor(() => expect(bars()).toHaveLength(24));

    await user.click(screen.getByRole("button", { name: "다음 날" }));

    await waitFor(() =>
      expect(urls).toContain("/api/timeline?day=2026-10-11&mode=self_low"),
    );
    expect(await screen.findByText("10월 11일 (일)")).toBeInTheDocument();
  });

  test("이전 날 버튼은 하루 앞을 부른다", async () => {
    const user = userEvent.setup();
    const { urls } = stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
    await waitFor(() => expect(bars()).toHaveLength(24));

    await user.click(screen.getByRole("button", { name: "이전 날" }));

    await waitFor(() =>
      expect(urls).toContain("/api/timeline?day=2026-10-09&mode=self_low"),
    );
  });

  test("충전 방식을 바꾸면 그 방식으로 다시 부른다", async () => {
    const user = userEvent.setup();
    const { urls } = stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
    await waitFor(() => expect(bars()).toHaveLength(24));

    await user.click(screen.getByRole("radio", { name: "공공 급속" }));

    await waitFor(() =>
      expect(urls).toContain("/api/timeline?day=2026-10-10&mode=public_fast"),
    );
  });

  test("날짜와 방식이 바뀌면 URL에 남길 수 있게 밖으로 알린다", async () => {
    const user = userEvent.setup();
    stubFetch(() => ({ body: timeline() }));
    const onQueryChange = vi.fn();

    render(
      <TimelineScreen
        initialDay="2026-10-10"
        initialMode="self_low"
        onQueryChange={onQueryChange}
      />,
    );

    await waitFor(() =>
      expect(onQueryChange).toHaveBeenCalledWith({ day: "2026-10-10", mode: "self_low" }),
    );

    await user.click(screen.getByRole("button", { name: "다음 날" }));

    await waitFor(() =>
      expect(onQueryChange).toHaveBeenCalledWith({ day: "2026-10-11", mode: "self_low" }),
    );
  });

/*
 * 태양광 예측은 기상청 호출이라 늘 받아두지 않는다. 버튼을 켤 때만 부르고,
 * 켤 수 없으면 켜진 척하지 않고 "준비 중"으로 돌아간다.
 */
describe("태양광 겹쳐 보기", () => {
  const SOLAR = {
    region: "전남",
    day: "2026-10-10",
    model_version: "v1",
    grid_nx: 51,
    grid_ny: 67,
    base_date: "20261010",
    base_time: "0500",
    installed_capacity_mw: null,
    capacity_source: null,
    assumptions: [
      "전남 전체를 기상청 5km 격자 한 칸(nx=57, ny=71)의 예보로 대신합니다.",
      "기상청 단기예보 20260921 2000 발표를 사용했습니다.",
    ],
    hours: [
      { hour: 12, ghi_wm2: 811, clear_sky_ghi_wm2: 1000, output_index: 0.811,
        predicted_mwh: null, sky: "1", pty: "0" },
    ],
  };

  function solarButton() {
    return screen.getAllByRole("button", { name: /태양광 발전 예측 겹쳐 보기/ })[0];
  }

  test("켜기 전에는 예측을 부르지 않는다", async () => {
    const { urls } = stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
    await screen.findAllByRole("button", { name: /태양광 발전 예측 겹쳐 보기/ });

    expect(urls.some((url) => url.startsWith("/api/solar-forecast"))).toBe(false);
  });

  test("켜면 그 날짜로 부르고 전제를 함께 보여준다", async () => {
    const user = userEvent.setup();
    const { urls } = stubFetch((url) =>
      url.startsWith("/api/solar-forecast") ? { body: SOLAR } : { body: timeline() },
    );

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
    await user.click(solarButton());

    await waitFor(() =>
      expect(urls.some((url) => url.includes("day=2026-10-10"))).toBe(true),
    );
    expect(await screen.findByText(/nx=57, ny=71/)).toBeInTheDocument();
    expect(screen.getByText(/20260921 2000 발표/)).toBeInTheDocument();
  });

  /* 켤 수 없으면 켜진 척하지 않는다 — 빈 오버레이가 "해가 없다"로 읽힌다. */
  test("501이면 켜지 않고 준비 중으로 돌아간다", async () => {
    const user = userEvent.setup();
    stubFetch((url) =>
      url.startsWith("/api/solar-forecast")
        ? { status: 501, body: { detail: "태양광 발전 예측은 아직 준비되지 않았습니다." } }
        : { body: timeline() },
    );

    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
    await user.click(solarButton());

    await waitFor(() => expect(solarButton()).toBeDisabled());
    expect(solarButton()).toHaveTextContent("준비 중");
  });
});

  test("URL에 날짜가 없으면 마운트 뒤에 오늘로 부른다", async () => {
    const { urls } = stubFetch(() => ({ body: timeline() }));

    render(<TimelineScreen initialMode="self_low" />);

    await waitFor(() => expect(urls.filter((url) => url.startsWith("/api/timeline"))).toHaveLength(1));
    // /health도 같은 목록에 쌓인다. 단가 요청만 골라 본다.
    const timelineUrls = urls.filter((url) => url.startsWith("/api/timeline"));
    expect(timelineUrls[0]).toMatch(/^\/api\/timeline\?day=\d{4}-\d{2}-\d{2}&mode=self_low$/);
  });
});

describe("TimelineScreen 서버 렌더", () => {
  /*
   * '오늘'을 서버 렌더에서 확정하면 서버(UTC 컨테이너)와 클라이언트(브라우저 표준시)가
   * 다른 날짜를 그려 hydration이 깨진다. 날짜가 주어지지 않은 첫 렌더에는
   * 날짜가 한 글자도 나오면 안 된다 — 마운트 뒤에 채운다.
   */
  test("날짜를 안 받으면 첫 렌더에 날짜를 찍지 않는다", () => {
    const html = renderToStaticMarkup(<TimelineScreen initialMode="self_low" />);

    expect(html).not.toMatch(/\d+월 \d+일/);
  });

  test("URL로 날짜를 받았으면 첫 렌더부터 그 날짜를 찍는다", () => {
    const html = renderToStaticMarkup(
      <TimelineScreen initialDay="2026-10-10" initialMode="self_low" />,
    );

    expect(html).toContain("10월 10일 (토)");
  });
});

/*
 * 단가 각주가 "예시 값 · 요금표 확정 후 바뀝니다"로 고정돼 있었다.
 * 한전 공식 요금표가 들어오면서 자가 저압 단가는 확정됐는데 각주만 남아 거짓말이 됐다.
 * 이제 /health가 알려주는 실제 미확인 항목에서 문장을 만든다.
 */
describe("단가 각주", () => {
  function renderWithHealth(health: { status?: number; body: unknown }) {
    stubFetch((url) =>
      url.startsWith("/health") ? health : { body: timeline() },
    );
    render(<TimelineScreen initialDay="2026-10-10" initialMode="self_low" />);
  }

  test("남은 미확인 항목만 말한다", async () => {
    renderWithHealth({
      body: { status: "ok", unverified_tariff_items: ["public_fast.base_price_per_kwh"] },
    });

    expect(
      await screen.findByText(/공공 급속 단가는 공식 요금표 확인 전 값입니다/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/예시 값/)).not.toBeInTheDocument();
  });

  test("전부 확인됐으면 잠정치라고 말하지 않는다", async () => {
    renderWithHealth({ body: { status: "ok", unverified_tariff_items: [] } });

    expect(await screen.findByText(/한국전력공사 전기요금표/)).toBeInTheDocument();
    expect(screen.queryByText(/확인 전 값입니다/)).not.toBeInTheDocument();
    expect(screen.queryByText(/예시 값/)).not.toBeInTheDocument();
  });

  /* /health를 못 받아도 단가 화면은 그대로 서야 한다. */
  test("확인 상태를 못 받아도 차트는 그대로 나온다", async () => {
    renderWithHealth({ status: 500, body: "boom" });

    expect(await screen.findAllByText("경부하")).not.toHaveLength(0);
  });
});

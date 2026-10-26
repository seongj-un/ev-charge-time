import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { HourPrice, TimelineResponse } from "@/lib/api/types";

import { TimelinePage } from "./TimelinePage";

/*
 * 날짜와 충전 방식이 URL에 남아야 새로고침·공유가 된다.
 * next/navigation은 앱 밖에서 못 도니 라우터만 가짜로 세운다.
 */

const replace = vi.fn();
let search = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => search,
}));

function hours(): HourPrice[] {
  return Array.from({ length: 24 }, (_, hour) => ({
    hour,
    band: "light" as const,
    discounted: false,
    price_per_kwh: 113.0,
  }));
}

function timeline(day: string): TimelineResponse {
  return { day, mode: "self_low", season: "winter", is_holiday: false, hours: hours() };
}

const urls: string[] = [];

beforeEach(() => {
  urls.length = 0;
  replace.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      return new Response(JSON.stringify(timeline("2026-01-14")), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TimelinePage", () => {
  test("URL의 날짜와 방식으로 부른다", async () => {
    search = new URLSearchParams("day=2026-01-14&mode=public_fast");

    render(<TimelinePage />);

    await waitFor(() =>
      expect(urls).toContain("/api/timeline?day=2026-01-14&mode=public_fast"),
    );
  });

  test("날짜가 바뀌면 URL을 갈아 끼운다 (히스토리를 쌓지 않는다)", async () => {
    const user = userEvent.setup();
    search = new URLSearchParams("day=2026-01-14&mode=self_low");

    render(<TimelinePage />);
    await waitFor(() => expect(urls.length).toBeGreaterThan(0));

    await user.click(screen.getByRole("button", { name: "다음 날" }));

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/timeline?day=2026-01-15&mode=self_low", {
        scroll: false,
      }),
    );
  });

  test("URL의 공용 급속 단가로 부르고, 바뀐 주소에도 남긴다", async () => {
    search = new URLSearchParams("day=2026-01-14&mode=public_fast&public_base_price=350");

    render(<TimelinePage />);

    await waitFor(() =>
      expect(urls).toContain(
        "/api/timeline?day=2026-01-14&mode=public_fast&public_base_price=350",
      ),
    );
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(
        "/timeline?day=2026-01-14&mode=public_fast&public_base_price=350",
        { scroll: false },
      ),
    );
  });

  test("알아볼 수 없는 쿼리는 무시하고 기본값으로 간다", async () => {
    // 주소창을 손으로 고친 경우. 2월 30일을 그대로 보내면 백엔드가 422만 준다.
    search = new URLSearchParams("day=2026-02-30&mode=self_medium");

    render(<TimelinePage />);

    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    // /health도 같은 목록에 쌓인다. 단가 요청만 골라 본다.
    const timelineUrls = urls.filter((url) => url.startsWith("/api/timeline"));
    expect(timelineUrls[0]).toMatch(/^\/api\/timeline\?day=\d{4}-\d{2}-\d{2}&mode=self_low$/);
    expect(timelineUrls[0]).not.toContain("2026-02-30");
  });
});

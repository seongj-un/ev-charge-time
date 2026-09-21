import { afterEach, describe, expect, test, vi } from "vitest";

import { ApiError, apiGet, apiPost, messageFromDetail } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

/*
 * FastAPI는 오류를 두 가지 모양으로 보낸다 (API 명세서 1장).
 *   - 업무 오류: detail이 문자열      → 그대로 사용자에게 보여준다
 *   - 필드 검증 실패: detail이 배열   → 사람이 읽을 문장으로 바꿔야 한다
 * 이걸 화면마다 풀면 같은 분기가 네 군데 생긴다. 한 곳에서 문장으로 만든다.
 */
describe("messageFromDetail", () => {
  test("업무 오류 문자열은 그대로 쓴다", () => {
    expect(
      messageFromDetail("시간이 부족합니다: 충전에 7:00:00 필요, 가능한 시간은 2:00:00."),
    ).toBe("시간이 부족합니다: 충전에 7:00:00 필요, 가능한 시간은 2:00:00.");
  });

  test("검증 실패 배열은 필드 이름을 붙여 한 문장으로 만든다", () => {
    expect(
      messageFromDetail([
        { loc: ["body", "soc_target"], msg: "soc_target은 soc_now보다 커야 합니다.", type: "value_error" },
      ]),
    ).toBe("soc_target: soc_target은 soc_now보다 커야 합니다.");
  });

  test("검증 실패가 여러 건이면 줄바꿈으로 잇는다", () => {
    expect(
      messageFromDetail([
        { loc: ["body", "soc_now"], msg: "0 이상이어야 합니다", type: "value_error" },
        { loc: ["body", "charger_kw"], msg: "0보다 커야 합니다", type: "value_error" },
      ]),
    ).toBe("soc_now: 0 이상이어야 합니다\ncharger_kw: 0보다 커야 합니다");
  });

  test("모양을 못 알아보면 일반 문장으로 돌아간다", () => {
    expect(messageFromDetail(undefined)).toBe("요청을 처리하지 못했습니다.");
  });
});

describe("apiPost", () => {
  test("성공하면 본문을 돌려준다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ savings_won: 399 }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(apiPost("/api/recommend", { soc_now: 30 })).resolves.toEqual({
      savings_won: 399,
    });
  });

  test("422면 detail을 담은 ApiError를 던진다", async () => {
    // Response 본문은 한 번만 읽힌다. 호출마다 새로 만들어 준다.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () =>
          new Response(JSON.stringify({ detail: "시간이 부족합니다." }), {
            status: 422,
            headers: { "content-type": "application/json" },
          }),
      ),
    );

    const error = await apiPost("/api/recommend", {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).message).toBe("시간이 부족합니다.");
  });

  test("501 스텁은 아직 준비되지 않았다고 알린다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "주변 충전소 조회는 아직 구현되지 않았습니다." }), {
          status: 501,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const error = await apiPost("/api/chargers", {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(501);
    expect((error as ApiError).notImplemented).toBe(true);
  });

  test("서버가 안 떠 있으면 연결 실패를 알린다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const error = await apiPost("/api/recommend", {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toContain("서버에 연결하지 못했습니다");
  });
});

describe("apiGet", () => {
  test("쿼리를 URL에 붙인다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ day: "2026-10-10" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiGet("/api/timeline", { day: "2026-10-10", mode: "self_low" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/timeline?day=2026-10-10&mode=self_low");
  });

  test("값이 없는 쿼리는 붙이지 않는다", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiGet("/api/timeline", { day: "2026-10-10", public_base_price: undefined });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/timeline?day=2026-10-10");
  });
});

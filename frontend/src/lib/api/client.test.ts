import { afterEach, describe, expect, test, vi } from "vitest";

import {
  ApiError,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  messageFromDetail,
} from "./client";

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

/*
 * 204를 돌려주는 엔드포인트가 여럿이다 (로그아웃, 즐겨찾기 추가·해제, 차량·계획 삭제).
 * 본문이 없는데 json()을 부르면 터지므로, 상태 코드로 먼저 갈라야 한다.
 */
describe("본문 없는 응답", () => {
  test("204면 본문을 읽지 않는다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response(null, { status: 204 })),
    );
    await expect(apiDelete("/api/me/favorites/ST-1")).resolves.toBeUndefined();
  });

  test("PUT도 204를 그대로 넘긴다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => new Response(null, { status: 204 })),
    );
    await expect(apiPut("/api/me/favorites/ST-1")).resolves.toBeUndefined();
  });
});

describe("apiPatch", () => {
  test("본문을 JSON으로 보낸다", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ id: "v1" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiPatch("/api/me/vehicles/v1", { name: "새 이름" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ name: "새 이름" });
  });
});

describe("apiDelete", () => {
  test("본문이 필요한 삭제도 보낼 수 있다", async () => {
    // DELETE /api/me 는 비밀번호 재확인을 본문으로 받는다.
    const fetchMock = vi
      .fn()
      .mockImplementation(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiDelete("/api/me", { password: "password123" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("DELETE");
    expect(JSON.parse(init.body)).toEqual({ password: "password123" });
  });
});

/*
 * 백엔드가 꺼지면 브라우저 fetch는 성공한다. 죽은 건 업스트림이고, 그 사이에 있는
 * Next의 rewrite 프록시가 500 + 평문 "Internal Server Error"를 돌려주기 때문이다.
 * 그래서 "서버에 닿지 못했다"를 status 0으로만 판정하면 프록시 환경에서 절대 안 잡힌다.
 */
describe("백엔드가 죽었을 때", () => {
  test("프록시가 준 500 평문은 연결 실패로 읽는다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () => new Response("Internal Server Error", { status: 500 }),
      ),
    );

    const error = await apiGet("/api/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain("서버에 연결하지 못했습니다");
    expect((error as ApiError).unreachable).toBe(true);
  });

  test("fetch 자체가 터진 경우도 연결 실패다", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const error = await apiGet("/api/me").catch((e: unknown) => e);
    expect((error as ApiError).unreachable).toBe(true);
  });

  test("서버가 제대로 답한 500은 그 메시지를 살린다", async () => {
    // 백엔드가 살아 있고 진짜 서버 오류를 낸 경우다. 연결 문제로 둔갑시키면
    // "백엔드를 켜세요"라는 엉뚱한 안내를 하게 된다.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () =>
          new Response(JSON.stringify({ detail: "요금표를 읽지 못했습니다." }), {
            status: 500,
            headers: { "content-type": "application/json" },
          }),
      ),
    );

    const error = await apiGet("/api/me").catch((e: unknown) => e);
    expect((error as ApiError).message).toBe("요금표를 읽지 못했습니다.");
    expect((error as ApiError).unreachable).toBe(false);
  });

  test("401은 연결 실패가 아니다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () =>
          new Response(JSON.stringify({ detail: "로그인이 필요합니다." }), {
            status: 401,
            headers: { "content-type": "application/json" },
          }),
      ),
    );

    const error = await apiGet("/api/me").catch((e: unknown) => e);
    expect((error as ApiError).unreachable).toBe(false);
    expect((error as ApiError).needsLogin).toBe(true);
  });
});

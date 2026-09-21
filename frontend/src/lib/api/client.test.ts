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
    ).toBe("목표 충전량: soc_target은 soc_now보다 커야 합니다.");
  });

  test("검증 실패가 여러 건이면 줄바꿈으로 잇는다", () => {
    expect(
      messageFromDetail([
        { loc: ["body", "soc_now"], msg: "0 이상이어야 합니다", type: "value_error" },
        { loc: ["body", "charger_kw"], msg: "0보다 커야 합니다", type: "value_error" },
      ]),
    ).toBe("현재 충전량: 0 이상이어야 합니다\n충전기 출력: 0보다 커야 합니다");
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

/*
 * 422 배열은 FastAPI가 만드는 필드별 오류다. loc과 msg를 그대로 이으면
 * "battery_kwh: Input should be greater than 0" 같은 영어 기술 문구가 화면에 뜬다.
 * 화면마다 이걸 풀면 같은 번역이 네 군데 생기므로 여기서 한 번에 우리말로 만든다.
 */
describe("필드 검증 실패를 우리말로", () => {
  test("필드 이름을 화면에 쓰는 말로 바꾼다", () => {
    expect(
      messageFromDetail([
        { type: "greater_than", loc: ["body", "battery_kwh"], msg: "Input should be greater than 0", ctx: { gt: 0 } },
      ]),
    ).toBe("배터리 용량: 0보다 커야 해요.");
  });

  test("여러 건은 줄바꿈으로 잇는다", () => {
    expect(
      messageFromDetail([
        { type: "greater_than", loc: ["body", "charger_kw"], msg: "x", ctx: { gt: 0 } },
        { type: "missing", loc: ["body", "deadline"], msg: "Field required" },
      ]),
    ).toBe("충전기 출력: 0보다 커야 해요.\n완료 시각: 값이 필요해요.");
  });

  test("범위 조건은 경계값을 그대로 말한다", () => {
    expect(
      messageFromDetail([
        { type: "less_than_equal", loc: ["body", "soc_target"], msg: "x", ctx: { le: 100 } },
      ]),
    ).toBe("목표 충전량: 100 이하여야 해요.");
    expect(
      messageFromDetail([
        { type: "string_too_short", loc: ["body", "password"], msg: "x", ctx: { min_length: 8 } },
      ]),
    ).toBe("비밀번호: 8자 이상이어야 해요.");
  });

  /*
   * 백엔드가 직접 던진 ValueError는 이미 우리말이다. pydantic이 앞에 붙이는
   * "Value error, "만 떼고 그대로 쓴다 — 우리가 다시 쓰면 뜻이 흐려진다.
   */
  test("백엔드가 쓴 우리말 메시지는 그대로 살린다", () => {
    expect(
      messageFromDetail([
        {
          type: "value_error",
          loc: ["body", "soc_target"],
          msg: "Value error, soc_target은 soc_now보다 커야 합니다.",
        },
      ]),
    ).toBe("목표 충전량: soc_target은 soc_now보다 커야 합니다.");
  });

  test("모르는 필드는 원래 이름을 남긴다", () => {
    // 백엔드가 새 필드를 추가해도 화면이 빈 문장을 내놓지 않아야 한다.
    expect(
      messageFromDetail([
        { type: "missing", loc: ["body", "brand_new_field"], msg: "Field required" },
      ]),
    ).toBe("brand_new_field: 값이 필요해요.");
  });

  test("모르는 검증 종류는 백엔드 문장을 그대로 쓴다", () => {
    expect(
      messageFromDetail([
        { type: "some_future_rule", loc: ["body", "email"], msg: "must be reachable" },
      ]),
    ).toBe("이메일: must be reachable");
  });

  test("본문이 아닌 곳의 오류도 필드를 밝힌다", () => {
    // 쿼리 파라미터 오류는 loc이 ["query", "month"]로 온다.
    expect(
      messageFromDetail([
        { type: "string_pattern_mismatch", loc: ["query", "month"], msg: "x" },
      ]),
    ).toContain("월");
  });
});

/*
 * 백엔드가 추가한 검증들. 라이브 응답을 그대로 옮겨 왔다.
 */
describe("백엔드가 새로 거르는 입력", () => {
  test("이메일 형식 오류는 우리말로 바꾼다", () => {
    // pydantic EmailStr은 value_error로 오지만 msg가 영어다. 그대로 살리면 샌다.
    expect(
      messageFromDetail([
        {
          type: "value_error",
          loc: ["body", "email"],
          msg: "value is not a valid email address: An email address must have an @-sign.",
          ctx: { reason: "An email address must have an @-sign." },
        },
      ]),
    ).toBe("이메일: 이메일 형식이 올바르지 않아요.");
  });

  /*
   * 모델 전체를 보는 검증(model_validator)은 loc이 ["body"]뿐이라 필드가 없다.
   * 필드 이름 없이 문장만 보여줘야 한다 — ": " 같은 빈 접두사가 붙으면 안 된다.
   */
  test("필드가 없는 검증은 문장만 보여준다", () => {
    expect(
      messageFromDetail([
        {
          type: "value_error",
          loc: ["body"],
          msg: "Value error, earliest_start와 deadline 사이는 14일을 넘을 수 없습니다.",
        },
      ]),
    ).toBe("earliest_start와 deadline 사이는 14일을 넘을 수 없습니다.");
  });

  test("길이 제한은 경계값과 함께 말한다", () => {
    expect(
      messageFromDetail([
        {
          type: "string_too_long",
          loc: ["body", "nickname"],
          msg: "String should have at most 50 characters",
          ctx: { max_length: 50 },
        },
      ]),
    ).toBe("닉네임: 50자 이하여야 해요.");
  });
});

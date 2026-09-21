import type { PlanSummary, User, Vehicle } from "@/lib/api/types";

/**
 * 마이페이지 테스트가 공유하는 fetch 스텁.
 *
 * 화면마다 따로 만들면 "어떤 요청이 나갔는가"를 보는 방식이 화면마다 달라진다.
 * 이 화면들의 계약은 전부 "무슨 요청을 언제 보냈나"라서, 호출 기록을 한 모양으로
 * 남겨 두는 편이 테스트를 읽기 쉽게 만든다.
 */
export type ApiCall = { url: string; method: string; body: unknown };

export type Route = { status?: number; body?: unknown };

export const USER: User = {
  id: "u1",
  email: "driver@example.com",
  nickname: "충전러",
  created_at: "2026-09-01T10:00:00+09:00",
};

export const COMMUTE: Vehicle = {
  id: "v1",
  name: "출퇴근 차",
  battery_kwh: 70,
  charger_kw: 7,
  mode: "self_low",
  is_default: true,
};

export const WEEKEND: Vehicle = {
  id: "v2",
  name: "주말 차",
  battery_kwh: 60,
  charger_kw: 3.5,
  mode: "public_fast",
  is_default: false,
};

export const EMPTY_SUMMARY: PlanSummary = {
  month: "2026-09",
  count: 0,
  total_savings_won: 0,
};

/** 로그인한 사용자에게 정상 응답을 주는 기본 라우트 */
export function okRoutes(
  options: { vehicles?: Vehicle[]; summary?: PlanSummary } = {},
): (call: ApiCall) => Route {
  const vehicles = options.vehicles ?? [COMMUTE, WEEKEND];
  const summary = options.summary ?? EMPTY_SUMMARY;
  return (call) => {
    if (call.url === "/api/me" && call.method === "GET") return { body: USER };
    if (call.url === "/api/me/vehicles" && call.method === "GET") return { body: vehicles };
    if (call.url.startsWith("/api/me/plans/summary")) return { body: summary };
    return { status: 204 };
  };
}

/**
 * fetch를 세우고 호출 기록을 돌려준다. 배열은 살아 있는 참조라 렌더 뒤에 그대로 읽으면 된다.
 *
 * vi를 인자로 받는 이유: 테스트 파일마다 vi.stubGlobal을 부르면 afterEach의
 * unstubAllGlobals와 짝이 맞는지 한눈에 보인다.
 */
export function stubApi(
  stubGlobal: (name: string, value: unknown) => void,
  routes: (call: ApiCall) => Route,
): ApiCall[] {
  const calls: ApiCall[] = [];
  stubGlobal(
    "fetch",
    async (url: string, init?: RequestInit) => {
      const call: ApiCall = {
        url,
        method: init?.method ?? "GET",
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      };
      calls.push(call);
      const { status = 200, body = null } = routes(call);
      if (status === 204) return new Response(null, { status });
      return new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    },
  );
  return calls;
}

/** 특정 엔드포인트로 나간 호출만 고른다. */
export function callsTo(calls: ApiCall[], method: string, url: string): ApiCall[] {
  return calls.filter((call) => call.method === method && call.url.split("?")[0] === url);
}

/**
 * 주변 충전소의 위치 실패 보고를 받아 서버 로그에 한 줄 남긴다.
 *
 * /api 아래가 아닌 이유: /api/*는 Caddy가 백엔드로 보낸다. 진단 한 줄 때문에 백엔드를
 * 다시 배포할 이유가 없어 프론트 서버가 받는다. 좌표·IP는 남기지 않는다.
 */
const FAILURES = new Set(["denied", "unavailable", "timeout", "unsupported"]);
const PERMISSIONS = new Set(["granted", "denied", "prompt", "unknown"]);

export async function POST(request: Request): Promise<Response> {
  let failure = "invalid";
  let permission = "invalid";
  try {
    const body = (await request.json()) as { failure?: unknown; permission?: unknown };
    if (typeof body.failure === "string" && FAILURES.has(body.failure)) failure = body.failure;
    if (typeof body.permission === "string" && PERMISSIONS.has(body.permission)) {
      permission = body.permission;
    }
  } catch {
    // 형식이 틀린 보고는 invalid로 남긴다.
  }
  const ua = (request.headers.get("user-agent") ?? "").slice(0, 200);
  console.log(JSON.stringify({ event: "geo_failure", failure, permission, ua }));
  return new Response(null, { status: 204 });
}

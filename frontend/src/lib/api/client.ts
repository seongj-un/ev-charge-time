/**
 * 백엔드로 나가는 요청은 전부 여기를 지난다.
 *
 * 경로는 `/api/...`처럼 상대 경로로 쓴다. next.config.ts의 rewrite가 FastAPI로
 * 넘겨주기 때문에 브라우저 입장에선 동일 출처이고, 그래서 httpOnly 세션 쿠키가
 * 따로 손대지 않아도 실린다.
 */

/** FastAPI 422 검증 실패 항목 */
type ValidationItem = {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
  /** 경계값 등 검증 종류별 부가 정보 (gt, le, min_length …) */
  ctx?: Record<string, unknown>;
};

/**
 * 필드 이름 → 화면에 쓰는 말.
 *
 * 백엔드 필드명을 그대로 보여주면 "battery_kwh"가 화면에 뜬다. 여기 없는 필드는
 * 원래 이름을 남긴다 — 백엔드가 새 필드를 추가해도 빈 문장을 내놓지 않는다.
 */
const FIELD_LABEL: Record<string, string> = {
  battery_kwh: "배터리 용량",
  charger_kw: "충전기 출력",
  soc_now: "현재 충전량",
  soc_target: "목표 충전량",
  earliest_start: "충전 시작 가능 시각",
  deadline: "완료 시각",
  mode: "충전 방식",
  efficiency: "효율",
  public_base_price: "공공 급속 단가",
  vehicle_id: "차량",
  email: "이메일",
  password: "비밀번호",
  nickname: "닉네임",
  name: "별칭",
  is_default: "기본 차량 여부",
  month: "월",
  day: "날짜",
  limit: "개수",
  cursor: "페이지 커서",
  lat: "위도",
  lng: "경도",
  radius_m: "반경",
};

/**
 * pydantic 검증 종류 → 우리말 문장.
 *
 * 모르는 종류는 백엔드가 준 msg를 그대로 쓴다. 번역표를 다 채우려 들면 백엔드가
 * 규칙을 하나 추가할 때마다 화면이 빈 문장을 내놓는다.
 */
function ruleMessage(item: ValidationItem): string {
  const ctx = item.ctx ?? {};
  const raw = item.msg ?? "값이 올바르지 않습니다";

  switch (item.type) {
    case "missing":
      return "값이 필요해요.";
    case "greater_than":
      return `${ctx.gt}보다 커야 해요.`;
    case "greater_than_equal":
      return `${ctx.ge} 이상이어야 해요.`;
    case "less_than":
      return `${ctx.lt}보다 작아야 해요.`;
    case "less_than_equal":
      return `${ctx.le} 이하여야 해요.`;
    case "string_too_short":
      return `${ctx.min_length}자 이상이어야 해요.`;
    case "string_too_long":
      return `${ctx.max_length}자 이하여야 해요.`;
    case "value_error":
      /*
       * 백엔드가 던진 ValueError는 이미 우리말이라 접두사만 떼고 살린다.
       * 다만 pydantic EmailStr은 같은 type으로 영어를 보낸다 — 그것만 갈라낸다.
       */
      if (raw.startsWith("value is not a valid email address")) {
        return "이메일 형식이 올바르지 않아요.";
      }
      return raw.replace(/^Value error,\s*/, "");
    default:
      return raw;
  }
}

const CONNECTION_FAILED =
  "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하세요.";

export class ApiError extends Error {
  readonly status: number;
  /**
   * 서버의 답이 아니라 서버에 닿지 못한 것.
   *
   * 이걸 401과 구분해야 하는 이유: 백엔드가 꺼졌을 때 "로그인하세요"가 뜨면
   * 사용자는 로그인을 시도하고 또 실패한다. 원인을 영영 모른다.
   */
  readonly unreachable: boolean;

  constructor(status: number, message: string, unreachable = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.unreachable = unreachable;
  }

  /** 501 스텁 — 계약은 있으나 아직 구현되지 않은 엔드포인트 */
  get notImplemented(): boolean {
    return this.status === 501;
  }

  /** 로그인이 필요하거나 세션이 만료됨 */
  get needsLogin(): boolean {
    return this.status === 401;
  }
}

/**
 * FastAPI의 detail은 업무 오류일 땐 문자열, 필드 검증 실패일 땐 배열이다.
 * 둘 다 사람이 읽을 한 문장으로 만든다.
 */
export function messageFromDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim() !== "") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const lines = (detail as ValidationItem[])
      .map((item) => {
        // loc의 첫 칸은 값이 어디서 왔는지(body·query·path)라 사용자에겐 뜻이 없다.
        const path = (item.loc ?? []).slice(1).join(".");
        const field = FIELD_LABEL[path] ?? path;
        const message = ruleMessage(item);
        return field ? `${field}: ${message}` : message;
      })
      .filter(Boolean);
    if (lines.length > 0) return lines.join("\n");
  }

  return "요청을 처리하지 못했습니다.";
}

export type Query = Record<string, string | number | boolean | undefined | null>;

export async function apiGet<T>(path: string, query?: Query): Promise<T> {
  return request<T>(withQuery(path, query), { method: "GET" });
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return withBody<T>("POST", path, body);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return withBody<T>("PATCH", path, body);
}

/** 즐겨찾기 추가처럼 본문 없이 경로만으로 성립하는 PUT도 있다. */
export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return withBody<T>("PUT", path, body);
}

/** DELETE /api/me 는 비밀번호 재확인을 본문으로 받는다. 나머지는 본문이 없다. */
export async function apiDelete<T>(path: string, body?: unknown): Promise<T> {
  return withBody<T>("DELETE", path, body);
}

function withBody<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(
    path,
    body === undefined
      ? { method }
      : {
          method,
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
  );
}

async function request<T>(url: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: "include" });
  } catch {
    // 원래 메시지("fetch failed")는 사용자에게 아무것도 알려주지 않는다.
    throw new ApiError(0, CONNECTION_FAILED, true);
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    /*
     * 백엔드가 꺼져도 브라우저 fetch는 성공한다. 죽은 건 업스트림이고, 사이에 있는
     * Next rewrite 프록시가 500 + 평문 "Internal Server Error"를 돌려주기 때문이다.
     * 그래서 detail을 못 읽은 5xx는 연결 실패로 본다. detail이 있으면 백엔드가
     * 살아서 답한 것이므로 그 메시지를 살린다 — 연결 문제로 둔갑시키면
     * "백엔드를 켜세요"라는 엉뚱한 안내를 하게 된다.
     */
    const gatewayFailure = response.status >= 500 && detail === undefined;
    throw new ApiError(
      response.status,
      gatewayFailure ? CONNECTION_FAILED : messageFromDetail(detail),
      gatewayFailure,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function readDetail(response: Response): Promise<unknown> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return body?.detail;
  } catch {
    return undefined;
  }
}

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const queryString = params.toString();
  return queryString ? `${path}?${queryString}` : path;
}

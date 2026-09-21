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
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
        const field = item.loc?.filter((part) => part !== "body").join(".");
        const message = item.msg ?? "값이 올바르지 않습니다";
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
    // 백엔드가 안 떠 있을 때가 대부분이다. 원래 메시지("fetch failed")는
    // 사용자에게 아무것도 알려주지 않으니 무엇을 해야 하는지로 바꿔 준다.
    throw new ApiError(0, "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하세요.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, messageFromDetail(await readDetail(response)));
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

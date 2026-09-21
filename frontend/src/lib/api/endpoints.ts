import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";
import type {
  ChatResponse,
  ChatTurn,
  FavoriteStation,
  HealthResponse,
  Mode,
  PlanSummary,
  RecommendRequest,
  RecommendResponse,
  SavedPlan,
  SavedPlanPage,
  SolarForecast,
  Station,
  TimelineResponse,
  User,
  Vehicle,
  VehicleInput,
} from "./types";

/** GET /health — F-08. 공식 확인이 안 끝난 요금 항목 목록을 함께 준다. */
export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}

/** GET /api/timeline — F-05·F-06. day는 임의 날짜 가능 (시뮬레이션). */
export function fetchTimeline(params: {
  day: string;
  mode?: Mode;
  publicBasePrice?: number;
}): Promise<TimelineResponse> {
  return apiGet<TimelineResponse>("/api/timeline", {
    day: params.day,
    mode: params.mode,
    public_base_price: params.publicBasePrice,
  });
}

/** POST /api/recommend — F-01·F-03·F-04. 게스트도 호출할 수 있다. */
export function fetchRecommendation(
  request: RecommendRequest,
): Promise<RecommendResponse> {
  return apiPost<RecommendResponse>("/api/recommend", request);
}

// ── 인증 (F-11) ─────────────────────────────────────────────────────────
//
// 세션은 httpOnly 쿠키다. 프론트가 읽을 수 없으므로 "로그인했나?"는
// GET /api/me를 불러 401인지로만 알 수 있다. SessionProvider가 그 일을 한다.

export function signup(body: {
  email: string;
  password: string;
  nickname?: string;
}): Promise<User> {
  return apiPost<User>("/api/auth/signup", body);
}

export function login(body: { email: string; password: string }): Promise<User> {
  return apiPost<User>("/api/auth/login", body);
}

export function logout(): Promise<void> {
  return apiPost<void>("/api/auth/logout", undefined);
}

export function fetchMe(): Promise<User> {
  return apiGet<User>("/api/me");
}

/** 탈퇴. 비밀번호로 재확인한다. 차량·충전 기록·즐겨찾기가 함께 지워진다. */
export function deleteAccount(password: string): Promise<void> {
  return apiDelete<void>("/api/me", { password });
}

// ── 내 차량 (F-12) ──────────────────────────────────────────────────────

export function fetchVehicles(): Promise<Vehicle[]> {
  return apiGet<Vehicle[]>("/api/me/vehicles");
}

/** is_default: true로 등록하면 기존 기본 차량은 서버가 자동 해제한다. */
export function createVehicle(body: VehicleInput): Promise<Vehicle> {
  return apiPost<Vehicle>("/api/me/vehicles", body);
}

export function updateVehicle(id: string, body: VehicleInput): Promise<Vehicle> {
  return apiPatch<Vehicle>(`/api/me/vehicles/${encodeURIComponent(id)}`, body);
}

export function deleteVehicle(id: string): Promise<void> {
  return apiDelete<void>(`/api/me/vehicles/${encodeURIComponent(id)}`);
}

// ── 충전 기록 (F-13) ────────────────────────────────────────────────────

/** month는 "YYYY-MM" (선택). limit은 1~100이며 범위 밖은 422 (API 명세서 7-3). */
export function fetchPlans(params?: {
  month?: string;
  limit?: number;
  cursor?: string;
}): Promise<SavedPlanPage> {
  return apiGet<SavedPlanPage>("/api/me/plans", {
    month: params?.month,
    limit: params?.limit,
    cursor: params?.cursor,
  });
}

/** month는 "YYYY-MM". 그 달의 건수와 savings_won 합계. */
export function fetchPlanSummary(month: string): Promise<PlanSummary> {
  return apiGet<PlanSummary>("/api/me/plans/summary", { month });
}

/**
 * 계획 저장. 본문은 추천 요청과 같은 모양이고, **서버가 다시 계산해서** 저장한다.
 * 클라이언트가 계산한 결과는 쓰지 않으므로 응답의 result를 화면에 써야 한다.
 *
 * vehicle_id를 함께 보내면 응답의 vehicle_name에 저장 시점 차량 이름이 박힌다.
 * 안 보내면 항상 null이라 기록 화면이 "어느 차로 세운 계획인지"를 영영 모른다.
 */
export function savePlan(
  request: RecommendRequest & { vehicle_id?: string },
): Promise<SavedPlan> {
  return apiPost<SavedPlan>("/api/me/plans", request);
}

export function deletePlan(id: string): Promise<void> {
  return apiDelete<void>(`/api/me/plans/${encodeURIComponent(id)}`);
}

// ── 충전소 (F-07, F-14) ─────────────────────────────────────────────────

/**
 * 주변 충전소. **아직 백엔드가 501이다.** 계약은 확정돼 있어 호출은 그대로 두고,
 * 화면이 ApiError.notImplemented를 받아 정직하게 알린다.
 * lat·lng는 조회에만 쓰이고 서버에 저장되지 않는다.
 */
export function fetchStations(params: {
  lat: number;
  lng: number;
  radiusM?: number;
  chargerType?: string;
}): Promise<Station[]> {
  return apiGet<Station[]>("/api/chargers", {
    lat: params.lat,
    lng: params.lng,
    radius_m: params.radiusM,
    charger_type: params.chargerType,
  });
}

/**
 * 즐겨찾는 충전소.
 *
 * 이름·주소는 F-07이 채우는 공유 캐시에서 온다. F-07이 501인 지금은
 * station_id만 채워지고 나머지는 null로 돌아온다 — 화면이 그 사실을 감추면 안 된다.
 */
export function fetchFavorites(): Promise<FavoriteStation[]> {
  return apiGet<FavoriteStation[]>("/api/me/favorites");
}

/** 멱등: 이미 즐겨찾기한 곳을 다시 불러도 204. */
export function addFavorite(stationId: string): Promise<void> {
  return apiPut<void>(`/api/me/favorites/${encodeURIComponent(stationId)}`);
}

export function removeFavorite(stationId: string): Promise<void> {
  return apiDelete<void>(`/api/me/favorites/${encodeURIComponent(stationId)}`);
}

// ── 태양광 발전 예측 (F-09) ─────────────────────────────────────────────

/**
 * 시도별 시간별 태양광 발전 예측.
 *
 * 차트에 겹칠 값은 `output_index`(0~1)다. `predicted_mwh`는 지금 항상 null이다.
 * `KMA_API_KEY`가 없으면 501이 온다 — 화면이 그 사실을 정직하게 알린다.
 */
export function fetchSolarForecast(params: {
  region: string;
  day: string;
}): Promise<SolarForecast> {
  return apiGet<SolarForecast>("/api/solar-forecast", {
    region: params.region,
    day: params.day,
  });
}

// ── 자연어 질의 (F-10) ──────────────────────────────────────────────────

/**
 * 질문 한 번. 로그인 필요.
 *
 * 올 수 있는 오류가 네 갈래이고 화면이 전부 다르게 말해야 한다:
 *   401 로그인 필요 · 501 `GEMINI_API_KEY` 없음 · 429 호출 제한(Retry-After)
 *   503 모델 쪽 일시 실패(재시도할 만함)
 *
 * `history`는 생략할 수 있지만, 되묻기("배터리 용량을 알려주세요") 다음 답을
 * 이어붙이려면 필요하다 — 안 보내면 서버는 매번 첫 질문으로 읽는다.
 */
export function askChat(params: {
  message: string;
  history?: ChatTurn[];
}): Promise<ChatResponse> {
  return apiPost<ChatResponse>("/api/chat", {
    message: params.message,
    ...(params.history && params.history.length > 0 ? { history: params.history } : {}),
  });
}

/**
 * 백엔드 `api/schemas.py`와 1:1로 맞춘 타입. 필드 이름도 snake_case 그대로 둔다.
 * 프론트 취향대로 camelCase로 바꾸면 응답을 볼 때마다 두 이름을 머릿속에서
 * 번역해야 하고, 그 번역 계층이 틀려도 타입 검사가 잡아주지 못한다.
 */

/** 충전 방식 */
export type Mode = "self_low" | "self_high" | "public_fast";

/** 부하 구간 */
export type Band = "light" | "middle" | "peak";

export type Season = "summer" | "spring_fall" | "winter";

export const MODE_LABEL: Record<Mode, string> = {
  self_low: "자가 저압",
  self_high: "자가 고압",
  public_fast: "공공 급속",
};

export const BAND_LABEL: Record<Band, string> = {
  light: "경부하",
  middle: "중간부하",
  peak: "최대부하",
};

export const SEASON_LABEL: Record<Season, string> = {
  summer: "여름",
  spring_fall: "봄·가을",
  winter: "겨울",
};

/** GET /health */
export type HealthResponse = {
  status: string;
  unverified_tariff_items: string[];
};

/** GET /api/timeline 의 시간 한 칸 */
export type HourPrice = {
  hour: number;
  band: Band;
  discounted: boolean;
  price_per_kwh: number;
};

/** GET /api/timeline */
export type TimelineResponse = {
  day: string;
  mode: Mode;
  season: Season;
  is_holiday: boolean;
  hours: HourPrice[];
};

/** POST /api/recommend 요청 */
export type RecommendRequest = {
  battery_kwh: number;
  soc_now: number;
  soc_target: number;
  charger_kw: number;
  /** 표준시 없는 ISO. 백엔드가 KST로 읽는다 (API 명세서 1장) */
  earliest_start: string;
  deadline: string;
  mode: Mode;
  public_base_price?: number;
  efficiency?: number;
};

export type ChargePlan = {
  start: string;
  end: string;
  energy_kwh: number;
  cost_won: number;
  /** 할인 구간에서 충전한 양 */
  discounted_kwh: number;
};

/** POST /api/recommend 응답 */
export type RecommendResponse = {
  best: ChargePlan;
  baseline_now: ChargePlan;
  savings_won: number;
  candidates_checked: number;
  assumptions: string[];
  unverified_tariff_items: string[];
};

// ── 인증·사용자 데이터 (F-11 ~ F-14) ─────────────────────────────────────

export type User = {
  id: string;
  email: string;
  nickname: string | null;
  created_at: string | null;
};

export type VehicleInput = {
  name: string;
  battery_kwh: number;
  charger_kw: number;
  mode: Mode;
  is_default: boolean;
};

export type Vehicle = VehicleInput & { id: string };

export type Charger = {
  charger_id: string;
  type: string;
  capacity_kw: number;
  status: string;
  status_updated_at: string | null;
};

/**
 * 충전소.
 *
 * ⚠️ 이 모양은 곧 바뀐다 (백엔드 세션 tropicbird-5a, 2026-09-21).
 * 지금은 즐겨찾기와 /api/chargers가 한 모델을 공유해서 전 필드가 선택이지만,
 * 즐겨찾기 전용 모델로 분리 중이고 /api/chargers는 전 필드 필수로 돌아간다.
 * **분리가 끝나기 전에는 이 타입에 기대는 화면을 만들지 않는다.**
 */
export type Station = {
  station_id: string;
  name: string | null;
  address: string | null;
  lat: number | null;
  lng: number | null;
  distance_m: number | null;
  operator: string | null;
  available_hours: string | null;
  /** 로그인 시 true/false, 게스트는 null */
  is_favorite: boolean | null;
  chargers: Charger[];
};

export type SavedPlan = {
  id: string;
  created_at: string;
  request: RecommendRequest;
  result: RecommendResponse;
  /** 계산에 쓴 요금 설정 버전. 저장 당시 값이며 재계산하지 않는다. */
  tariff_version: string;
};

export type SavedPlanPage = {
  items: SavedPlan[];
  next_cursor: string | null;
};

export type PlanSummary = {
  /** "YYYY-MM" */
  month: string;
  count: number;
  total_savings_won: number;
};

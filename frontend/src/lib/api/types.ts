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
 * 충전소 (F-07 `GET /api/chargers`).
 *
 * 이 경로는 캐시가 항상 차 있으므로 캐시 유래 필드가 전부 채워져 온다.
 * 즐겨찾기는 보장이 달라서 FavoriteStation으로 따로 둔다 (API 명세서 7-4).
 */
export type Station = {
  station_id: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  distance_m: number;
  operator: string;
  available_hours: string;
  /** 로그인 시 true/false, 게스트는 null */
  is_favorite: boolean | null;
  chargers: Charger[];
};

/**
 * 즐겨찾는 충전소 (F-14 `GET /api/me/favorites`).
 *
 * 즐겨찾기는 station_id만으로 성립한다. 이름·주소는 F-07이 채우는 공유 캐시에서
 * 오는데, F-07이 아직 501이라 **캐시 미적중이 예외가 아니라 기본 상태**다.
 *
 * 미적중이면 빈 문자열·0·빈 배열이 아니라 전부 null이다. chargers도 []가 아니라
 * null인데, []는 "충전기가 0대인 충전소"고 null은 "아직 못 불러왔다"라서
 * 화면이 다르게 표시해야 하기 때문이다 (API 명세서 7-4).
 */
export type FavoriteStation = {
  station_id: string;
  name: string | null;
  address: string | null;
  lat: number | null;
  lng: number | null;
  distance_m: number | null;
  operator: string | null;
  available_hours: string | null;
  is_favorite: boolean | null;
  chargers: Charger[] | null;
};

export type SavedPlan = {
  id: string;
  created_at: string;
  request: RecommendRequest;
  result: RecommendResponse;
  /** 계산에 쓴 요금 설정 버전. 저장 당시 값이며 재계산하지 않는다. */
  tariff_version: string;
  /** 저장 시점 차량 이름 스냅샷. 직접 입력했으면 null (API 명세서 7-3). */
  vehicle_name: string | null;
  /**
   * 충전을 시작하는 시각 (= result.best.start). 월 필터·정렬의 기준이다.
   *
   * 저장 시각(created_at)이 아니다. 9월에 세운 10월 충전 계획은 10월에 잡힌다 —
   * 사용자가 묻는 건 "10월에 얼마나 아끼나"이지 "9월에 계획을 몇 번 세웠나"가 아니다.
   */
  charge_start: string;
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

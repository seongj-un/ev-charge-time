import type { Mode, RecommendRequest } from "./api/types";

/**
 * 충전 조건을 URL 쿼리에 싣고 내리는 곳.
 *
 * 입력 화면(/recommend)과 결과 화면(/recommend/result)이 서로 다른 라우트라,
 * 조건을 어딘가에 담아 넘겨야 한다. 전역 상태에 두면 결과 화면에서
 * 새로고침하는 순간 빈 화면이 된다. URL에 실으면 새로고침·뒤로가기·링크 공유가
 * 전부 공짜로 따라온다. 심사 시연에서 링크 하나로 특정 추천을 바로 띄울 수 있다.
 *
 * 쿼리 이름은 백엔드 요청 필드와 똑같이 쓴다 — URL만 보고도 무슨 요청이 나갈지 안다.
 */

export type RecommendForm = {
  batteryKwh: number;
  chargerKw: number;
  socNow: number;
  socTarget: number;
  /** datetime-local 값. "2026-10-07T18:00" — 표준시를 붙이지 않는다. */
  earliestStart: string;
  deadline: string;
  mode: Mode;
  /**
   * 공공 급속 단가(원/kWh). 공공 급속일 때만 쓴다.
   *
   * 공공 급속은 충전사업자마다 단가가 달라 공식 값이 하나로 없다. 기본 설정의
   * 백엔드는 이 값 없이 공공 급속을 계산하지 않는다.
   */
  publicBasePrice?: number;
  /**
   * 고른 차량. 저장할 때만 쓴다.
   *
   * 추천 요청에는 싣지 않는다 — vehicle_id가 붙은 요청은 로그인을 요구해서,
   * 결과 URL을 공유받은 사람이 401을 맞는다. 값은 이미 폼에 복사돼 있으므로
   * 추천 결과는 똑같이 나온다.
   */
  vehicleId?: string;
};

const MODES: Mode[] = ["self_low", "self_high", "public_fast"];

export function toSearchParams(form: RecommendForm): URLSearchParams {
  const params = new URLSearchParams({
    battery_kwh: String(form.batteryKwh),
    charger_kw: String(form.chargerKw),
    soc_now: String(form.socNow),
    soc_target: String(form.socTarget),
    earliest_start: form.earliestStart,
    deadline: form.deadline,
    mode: form.mode,
  });
  if (form.mode === "public_fast" && form.publicBasePrice !== undefined) {
    params.set("public_base_price", String(form.publicBasePrice));
  }
  if (form.vehicleId) params.set("vehicle_id", form.vehicleId);
  return params;
}

/** 쿼리를 읽는다. 하나라도 모양이 안 맞으면 null — 반쪽짜리 조건으로 요청하지 않는다. */
export function fromSearchParams(
  params: URLSearchParams | { get(key: string): string | null },
): RecommendForm | null {
  const batteryKwh = readNumber(params.get("battery_kwh"));
  const chargerKw = readNumber(params.get("charger_kw"));
  const socNow = readNumber(params.get("soc_now"));
  const socTarget = readNumber(params.get("soc_target"));
  const earliestStart = params.get("earliest_start");
  const deadline = params.get("deadline");
  const mode = params.get("mode");

  if (
    batteryKwh === null ||
    chargerKw === null ||
    socNow === null ||
    socTarget === null ||
    !earliestStart ||
    !deadline ||
    !isMode(mode)
  ) {
    return null;
  }

  // 단가는 없어도 되지만(백엔드 설정에 기본값이 있을 수 있다), 있는데 못 읽으면
  // 반쪽짜리 조건이다. 0 이하도 단가가 아니다.
  const rawPrice = params.get("public_base_price");
  const publicBasePrice = rawPrice === null ? null : readNumber(rawPrice);
  if (rawPrice !== null && (publicBasePrice === null || publicBasePrice <= 0)) return null;

  const vehicleId = params.get("vehicle_id");
  return {
    batteryKwh,
    chargerKw,
    socNow,
    socTarget,
    earliestStart,
    deadline,
    mode,
    ...(mode === "public_fast" && publicBasePrice !== null ? { publicBasePrice } : {}),
    ...(vehicleId ? { vehicleId } : {}),
  };
}

/**
 * 백엔드 요청 모양으로 바꾼다.
 *
 * 시각에 표준시를 붙이지 않는 것이 중요하다. 백엔드는 표준시 없는 입력을 KST로
 * 읽는다 (API 명세서 1장). toISOString()을 쓰면 UTC로 바뀌어 9시간 어긋난
 * 추천이 돌아온다.
 */
export function toRecommendRequest(form: RecommendForm): RecommendRequest {
  const request: RecommendRequest = {
    battery_kwh: form.batteryKwh,
    charger_kw: form.chargerKw,
    soc_now: form.socNow,
    soc_target: form.socTarget,
    earliest_start: form.earliestStart,
    deadline: form.deadline,
    mode: form.mode,
  };
  if (form.mode === "public_fast" && form.publicBasePrice !== undefined) {
    request.public_base_price = form.publicBasePrice;
  }
  return request;
}

/**
 * 저장 요청. 추천 요청과 같은 모양에 vehicle_id만 더 얹는다.
 *
 * 이걸 안 보내면 SavedPlan.vehicle_name이 항상 null이라, 충전 기록이
 * "어느 차로 세운 계획인지"를 영영 모른다 (API 명세서 7-3).
 */
export function toSavePlanRequest(
  form: RecommendForm,
): RecommendRequest & { vehicle_id?: string } {
  const request = toRecommendRequest(form);
  return form.vehicleId ? { ...request, vehicle_id: form.vehicleId } : request;
}

const DAY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

/*
 * 시각 계산은 전부 "한국 벽시계"로 한다.
 *
 * 백엔드는 표준시 없는 시각을 한국 시각으로 읽는다. 브라우저의 getHours()·setHours()는
 * 기기 시간대를 따르므로, 해외(또는 UTC로 맞춘 기기)에서 기본값이 9시간 어긋났다 —
 * UTC 기기에서 한국 18:15에 열면 "09:30부터"가 채워졌다. 한국은 서머타임이 없어 늘
 * UTC+9이므로, 순간에 9시간을 더한 Date의 UTC 필드(getUTC*)를 한국 벽시계로 쓴다.
 * 이 Date들은 "순간"이 아니라 벽시계 값을 담는 그릇이다 — 밖으로는 문자열만 내보낸다.
 */
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

function kstWallClock(instant: Date): Date {
  return new Date(instant.getTime() + KST_OFFSET_MS);
}

/**
 * 특정 날짜로 계획할 때 채워 둘 시각.
 *
 * 하루 단가 화면에서 "이 날짜로 추천받기"로 넘어오면 그 날짜가 온다. '지금'과
 * 무관한 미래 날짜라 "지금부터"라는 기본값이 뜻이 없다. 그 날 저녁 18시부터
 * 다음날 아침 8시까지 — 이 앱이 상정하는 가장 흔한 쓰임이고 디자인 예시와도 같다.
 *
 * 읽을 수 없는 날짜면 null. 주소창은 누구나 고친다.
 */
export function timesForDay(day: string): { earliestStart: string; deadline: string } | null {
  const matched = DAY_PATTERN.exec(day);
  if (!matched) return null;
  const [, year, month, date] = matched;
  const start = new Date(Date.UTC(Number(year), Number(month) - 1, Number(date), 18, 0, 0, 0));
  // Date가 2026-13-99 같은 값을 조용히 굴려 버린다. 되읽어 확인한다.
  if (start.getUTCMonth() !== Number(month) - 1 || start.getUTCDate() !== Number(date)) {
    return null;
  }
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 1);
  end.setUTCHours(8, 0, 0, 0);
  return { earliestStart: formatWallClock(start), deadline: formatWallClock(end) };
}

/** 처음 열었을 때 채워 둘 값. 디자인의 예시(70 kWh · 7 kW · 30% → 60%)를 따른다. */
export function defaultForm(now: Date): RecommendForm {
  const start = ceilToHalfHour(kstWallClock(now));
  return {
    batteryKwh: 70,
    chargerKw: 7,
    socNow: 30,
    socTarget: 60,
    earliestStart: formatWallClock(start),
    deadline: formatWallClock(nextMorning(start)),
    mode: "self_low",
  };
}

/** datetime-local이 먹는 "YYYY-MM-DDTHH:mm" 문자열. 순간을 한국 시각으로 적는다. */
export function toLocalInput(date: Date): string {
  return formatWallClock(kstWallClock(date));
}

/** 벽시계 그릇(UTC 필드)을 "YYYY-MM-DDTHH:mm"로 */
function formatWallClock(wall: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${wall.getUTCFullYear()}-${pad(wall.getUTCMonth() + 1)}-${pad(wall.getUTCDate())}` +
    `T${pad(wall.getUTCHours())}:${pad(wall.getUTCMinutes())}`
  );
}

function ceilToHalfHour(wall: Date): Date {
  const result = new Date(wall);
  result.setUTCSeconds(0, 0);
  const minutes = result.getUTCMinutes();
  if (minutes === 0 || minutes === 30) return result;
  result.setUTCMinutes(minutes < 30 ? 30 : 60);
  return result;
}

/** 대부분 "밤에 꽂아두고 아침에 나간다". 기본 완료 시각을 그다음 아침 8시로 둔다. */
function nextMorning(from: Date): Date {
  const morning = new Date(from);
  morning.setUTCHours(8, 0, 0, 0);
  if (morning <= from) {
    morning.setUTCDate(morning.getUTCDate() + 1);
  }
  return morning;
}

function readNumber(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function isMode(value: string | null): value is Mode {
  return value !== null && (MODES as string[]).includes(value);
}

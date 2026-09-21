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
};

const MODES: Mode[] = ["self_low", "self_high", "public_fast"];

export function toSearchParams(form: RecommendForm): URLSearchParams {
  return new URLSearchParams({
    battery_kwh: String(form.batteryKwh),
    charger_kw: String(form.chargerKw),
    soc_now: String(form.socNow),
    soc_target: String(form.socTarget),
    earliest_start: form.earliestStart,
    deadline: form.deadline,
    mode: form.mode,
  });
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

  return { batteryKwh, chargerKw, socNow, socTarget, earliestStart, deadline, mode };
}

/**
 * 백엔드 요청 모양으로 바꾼다.
 *
 * 시각에 표준시를 붙이지 않는 것이 중요하다. 백엔드는 표준시 없는 입력을 KST로
 * 읽는다 (API 명세서 1장). toISOString()을 쓰면 UTC로 바뀌어 9시간 어긋난
 * 추천이 돌아온다.
 */
export function toRecommendRequest(form: RecommendForm): RecommendRequest {
  return {
    battery_kwh: form.batteryKwh,
    charger_kw: form.chargerKw,
    soc_now: form.socNow,
    soc_target: form.socTarget,
    earliest_start: form.earliestStart,
    deadline: form.deadline,
    mode: form.mode,
  };
}

/** 처음 열었을 때 채워 둘 값. 디자인의 예시(70 kWh · 7 kW · 30% → 60%)를 따른다. */
export function defaultForm(now: Date): RecommendForm {
  const start = ceilToHalfHour(now);
  return {
    batteryKwh: 70,
    chargerKw: 7,
    socNow: 30,
    socTarget: 60,
    earliestStart: toLocalInput(start),
    deadline: toLocalInput(nextMorning(start)),
    mode: "self_low",
  };
}

/** datetime-local이 먹는 "YYYY-MM-DDTHH:mm" 문자열 */
export function toLocalInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function ceilToHalfHour(date: Date): Date {
  const result = new Date(date);
  result.setSeconds(0, 0);
  const minutes = result.getMinutes();
  if (minutes === 0 || minutes === 30) return result;
  result.setMinutes(minutes < 30 ? 30 : 60);
  return result;
}

/** 대부분 "밤에 꽂아두고 아침에 나간다". 기본 완료 시각을 그다음 아침 8시로 둔다. */
function nextMorning(from: Date): Date {
  const morning = new Date(from);
  morning.setHours(8, 0, 0, 0);
  if (morning <= from) {
    morning.setDate(morning.getDate() + 1);
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

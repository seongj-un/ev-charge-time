import { parseKstWallClock } from "./format";

/**
 * 충전량·소요시간 계산. 백엔드 설계서의 식과 같은 것을 쓴다.
 *
 * 왜 프론트에도 두는가: 입력 화면이 "최적 시간 찾기"를 누르기 전에
 * "필요 충전량 21 kWh · 약 3시간"을 미리 보여준다. 이걸 서버에 물으면
 * 키 하나 칠 때마다 왕복이 생긴다. 추천 결과의 금액은 전부 서버 값을 쓰고,
 * 여기서 낸 값은 화면 미리보기로만 쓴다.
 */

export type EnergyInput = {
  batteryKwh: number;
  socNow: number;
  socTarget: number;
  /** 0 초과 1 이하. 기본 1.0 (API 명세서 2-2) */
  efficiency?: number;
};

/** 필요량 = 용량 × (목표 − 현재) / 100 / 효율 */
export function requiredEnergyKwh({
  batteryKwh,
  socNow,
  socTarget,
  efficiency = 1,
}: EnergyInput): number {
  const gap = socTarget - socNow;
  if (gap <= 0) return 0;
  return (batteryKwh * gap) / 100 / efficiency;
}

/** 소요시간 = 필요량 / 충전기 출력. 출력이 없으면 계산하지 않는다. */
export function estimateHours({
  energyKwh,
  chargerKw,
}: {
  energyKwh: number;
  chargerKw: number;
}): number | null {
  if (chargerKw <= 0) return null;
  return energyKwh / chargerKw;
}

/**
 * 구간이 걸친 시각(0–23)들. 차트 위 마커를 어느 막대에 그릴지 정하는 데 쓴다.
 *
 * 22:00 – 01:00처럼 자정을 넘는 구간이 흔하다. 날짜를 넘겨도 시각만 이어 세면
 * 되는 이유는, 차트가 24시간 원형이 아니라 "시작 시각부터 이어지는 축"이기 때문이다.
 * 끝 시각이 정시면 그 시각은 덮지 않는다 — 21:00에 끝났으면 21시 막대는 안 썼다.
 */
export function coveredHours(startIso: string, endIso: string): number[] {
  const start = parseKstWallClock(startIso);
  const end = parseKstWallClock(endIso);

  const startMinutes = start.hour * 60 + start.minute;
  const dayGap = daysBetween(start, end);
  const endMinutes = dayGap * 24 * 60 + end.hour * 60 + end.minute;

  const firstHour = Math.floor(startMinutes / 60);
  // 정시에 끝나면 직전 시각까지만 덮는다.
  const lastHour = Math.ceil(endMinutes / 60) - 1;

  const hours: number[] = [];
  for (let hour = firstHour; hour <= lastHour; hour += 1) {
    hours.push(((hour % 24) + 24) % 24);
  }
  return hours;
}

function daysBetween(from: WallClockDate, to: WallClockDate): number {
  const fromUtc = Date.UTC(from.year, from.month - 1, from.day);
  const toUtc = Date.UTC(to.year, to.month - 1, to.day);
  return Math.round((toUtc - fromUtc) / 86_400_000);
}

type WallClockDate = { year: number; month: number; day: number };

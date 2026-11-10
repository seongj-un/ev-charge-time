/**
 * 화면에 찍히는 문자열은 전부 여기를 거친다.
 *
 * 시각을 Date로 만들어 toLocaleString에 넘기지 않는 이유: 백엔드가 보내는 시각은
 * 항상 KST(+09:00)인데, Date로 만들면 브라우저 표준시로 다시 읽힌다. 심사위원
 * 노트북 표준시가 뭐든 "22:00 추천"은 22:00으로 보여야 한다. 그래서 ISO 문자열에
 * 적힌 벽시계 값을 그대로 꺼내 쓴다.
 */

export type WallClock = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

const ISO_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

/** ISO 문자열에 적힌 벽시계 값을 표준시 변환 없이 읽는다. */
export function parseKstWallClock(iso: string): WallClock {
  const matched = ISO_PATTERN.exec(iso);
  if (!matched) {
    throw new Error(`시각 형식을 읽을 수 없습니다: ${iso}`);
  }
  const [, year, month, day, hour, minute] = matched;
  return {
    year: Number(year),
    month: Number(month),
    day: Number(day),
    hour: Number(hour ?? 0),
    minute: Number(minute ?? 0),
  };
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"] as const;

/**
 * 지금 한국 날짜 "YYYY-MM-DD". 한국은 서머타임이 없어 늘 UTC+9다.
 * 기기 시간대를 따르지 않는다 — 해외 기기에서 열어도 한국 날짜다.
 */
export function kstToday(now: Date = new Date()): string {
  return new Date(now.getTime() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/** "22:00" */
export function formatHm(iso: string): string {
  const { hour, minute } = parseKstWallClock(iso);
  return `${pad2(hour)}:${pad2(minute)}`;
}

/** "10월 7일 (수)" */
export function formatKoreanDate(iso: string): string {
  const { year, month, day } = parseKstWallClock(iso);
  // 표준시가 끼어들지 않게 UTC 기준으로 요일만 구한다.
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return `${month}월 ${day}일 (${weekday})`;
}

/** "2,373원" */
export function formatWon(won: number): string {
  return `${Math.round(won).toLocaleString("ko-KR")}원`;
}

/**
 * "−399원" — 절감액용. 하이픈(-)이 아니라 빼기 기호(U+2212)를 쓴다.
 * 고정폭 숫자와 폭이 맞아서 금액이 세로로 줄을 선다.
 */
export function formatSignedWon(won: number): string {
  const amount = Math.round(won);
  return amount > 0 ? `−${formatWon(amount)}` : formatWon(amount);
}

/** "113.0" — 단가는 원/kWh 소수 첫째 자리 (API 명세서 1장) */
export function formatPricePerKwh(price: number): string {
  return price.toFixed(1);
}

/** "21 kWh" */
export function formatKwh(kwh: number): string {
  return `${round1(kwh)} kWh`;
}

/** "약 3시간" · "약 3시간 30분" */
export function formatDuration(hours: number): string {
  const totalMinutes = Math.round(hours * 60);
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (wholeHours === 0) return `약 ${minutes}분`;
  if (minutes === 0) return `약 ${wholeHours}시간`;
  return `약 ${wholeHours}시간 ${minutes}분`;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

import { bandKeyOf, type BandKey } from "@/components/chart/bands";
import type { PriceColumn } from "@/components/chart/PriceBarChart";
import { SEASON_LABEL, type HourPrice, type Mode, type TimelineResponse } from "@/lib/api/types";
import { formatPricePerKwh, parseKstWallClock } from "@/lib/format";

/**
 * 하루 단가 화면이 응답에서 문장과 막대를 뽑는 곳.
 *
 * 컴포넌트 안에 두지 않은 이유: 이 화면이 거짓말을 하는 경우는 거의 전부
 * "응답에 없는 걸 그렸다"이고(없는 할인 배너, 없는 부하구간 범례), 그건 렌더링이
 * 아니라 이 계산에서 갈린다. 렌더링 없이 테스트할 수 있어야 한다.
 */

/** 범례와 단가 목록에서 언제나 같은 순서로 읽히게 한다. 디자인의 순서다. */
const BAND_ORDER: BandKey[] = ["light", "middle", "peak", "discounted"];

/**
 * 단가는 백엔드에서 곱셈으로 나온다 — 71.2와 71.20000000000001이 같은 응답에 섞인다.
 * 같은 값인지 볼 때는 이만큼의 오차를 허용한다.
 */
const PRICE_EPSILON = 1e-6;

const MODES: Mode[] = ["self_low", "self_high", "public_fast"];

export function isMode(value: unknown): value is Mode {
  return typeof value === "string" && (MODES as string[]).includes(value);
}

/** 세그먼티드 컨트롤에 넘길 선택지 */
export const MODE_OPTIONS = MODES;

const DAY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * URL 쿼리는 누구나 고칠 수 있다. 2월 30일을 그대로 백엔드에 보내면 422만 받는다.
 * 형식뿐 아니라 달력에 실제로 있는 날인지까지 본다.
 */
export function isDay(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const matched = DAY_PATTERN.exec(value);
  if (!matched) return false;
  const [, year, month, day] = matched.map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

/**
 * KST 기준 오늘. 브라우저 표준시가 무엇이든 서비스의 '오늘'은 한국 날짜다.
 * en-CA 로캘이 YYYY-MM-DD를 준다.
 */
export function todayInSeoul(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

/**
 * 하루씩 앞뒤로. Date에 로컬 표준시로 넣으면 서머타임·표준시 경계에서 날짜가 튄다.
 * UTC 자정으로만 계산하면 어디서 돌려도 결과가 같다.
 */
export function shiftDay(day: string, delta: number): string {
  const { year, month, day: date } = parseKstWallClock(day);
  const moved = new Date(Date.UTC(year, month - 1, date + delta));
  return `${moved.getUTCFullYear()}-${pad2(moved.getUTCMonth() + 1)}-${pad2(moved.getUTCDate())}`;
}

/** 응답의 시간 목록 → 차트 컬럼. 할인이 걸린 시각은 부하구간과 무관하게 할인 색이다. */
export function toColumns(hours: HourPrice[]): PriceColumn[] {
  return hours.map((entry) => ({
    hour: entry.hour,
    bandKey: bandKeyOf(entry.band, entry.discounted),
    pricePerKwh: entry.price_per_kwh,
  }));
}

/** 최저 단가인 시각들. 차트 위 "최저 단가" 마커가 여기서 나온다. */
export function cheapestHours(hours: HourPrice[]): number[] {
  if (hours.length === 0) return [];
  const lowest = Math.min(...hours.map((entry) => entry.price_per_kwh));
  return hours
    .filter((entry) => entry.price_per_kwh - lowest <= PRICE_EPSILON)
    .map((entry) => entry.hour);
}

/**
 * 오늘 실제로 나타난 부하구간만. 최대부하가 없는 날에 범례가 "최대"를 띄우면
 * 범례와 막대가 맞지 않아 범례를 아무도 믿지 않게 된다.
 */
export function presentBandKeys(hours: HourPrice[]): BandKey[] {
  const seen = new Set(hours.map((entry) => bandKeyOf(entry.band, entry.discounted)));
  return BAND_ORDER.filter((key) => seen.has(key));
}

export type BandPriceRow = {
  key: BandKey;
  min: number;
  max: number;
};

/**
 * 부하구간마다 한 줄. 같은 구간 안에서도 단가가 다를 수 있어서(공공 급속의 기본단가
 * 가산, 계절 경계 등) 대표값 하나로 뭉개지 않고 최소·최대를 같이 들고 나간다.
 */
export function bandPriceRows(hours: HourPrice[]): BandPriceRow[] {
  const byKey = new Map<BandKey, number[]>();
  for (const entry of hours) {
    const key = bandKeyOf(entry.band, entry.discounted);
    const prices = byKey.get(key) ?? [];
    prices.push(entry.price_per_kwh);
    byKey.set(key, prices);
  }

  return BAND_ORDER.filter((key) => byKey.has(key)).map((key) => {
    const prices = byKey.get(key)!;
    return { key, min: Math.min(...prices), max: Math.max(...prices) };
  });
}

/**
 * "113.0" 또는 "113.0–120.5".
 *
 * 화면에 찍히는 문자열이 같으면 범위로 쓰지 않는다 — 113.00과 113.04는 둘 다
 * "113.0"이라 "113.0–113.0"이 되고, 이건 정보가 아니라 잡음이다.
 */
export function formatBandPrice(row: BandPriceRow): string {
  const min = formatPricePerKwh(row.min);
  const max = formatPricePerKwh(row.max);
  return min === max ? min : `${min}–${max}`;
}

/**
 * "11–14시" — 할인이 걸린 시각들을 이어 붙인 반개구간.
 * 11·12·13시가 할인이면 "11시부터 14시까지"다. 끝을 13으로 적으면 한 시간이 사라진다.
 * 할인이 하나도 없으면 null이고, 그때 배너를 띄우면 안 된다.
 */
export function discountRangeLabel(hours: HourPrice[]): string | null {
  const discounted = hours
    .filter((entry) => entry.discounted)
    .map((entry) => entry.hour)
    .sort((a, b) => a - b);
  if (discounted.length === 0) return null;

  const ranges: string[] = [];
  let start = discounted[0];
  let previous = discounted[0];
  for (const hour of discounted.slice(1)) {
    if (hour !== previous + 1) {
      ranges.push(`${start}–${previous + 1}시`);
      start = hour;
    }
    previous = hour;
  }
  ranges.push(`${start}–${previous + 1}시`);
  return ranges.join(", ");
}

/** 응답에 할인이 걸린 시각이 실제로 있는가. 배너를 띄울지 말지의 유일한 근거다. */
export function hasDiscount(hours: HourPrice[]): boolean {
  return hours.some((entry) => entry.discounted);
}

/** "공휴일" · "주말" · "평일". 요금이 갈리는 기준이라 공휴일이 주말보다 앞선다. */
export function dayTypeLabel(day: string, isHoliday: boolean): string {
  if (isHoliday) return "공휴일";
  const { year, month, day: date } = parseKstWallClock(day);
  const weekday = new Date(Date.UTC(year, month - 1, date)).getUTCDay();
  return weekday === 0 || weekday === 6 ? "주말" : "평일";
}

/**
 * "시뮬레이션 · 봄·가을 주말".
 *
 * 하드코딩하지 않는다 — 임의 날짜를 넣어 볼 수 있는 화면이라 부제가 날짜를 따라가지
 * 않으면 10월 화면에 "가을 주말"이 남은 채 1월이 그려진다.
 * '시뮬레이션'을 늘 붙이는 이유: 이 단가는 확정되지 않은 요금표로 계산한 추정이고,
 * 오늘을 보든 내년을 보든 그 사실은 바뀌지 않는다.
 */
export function daySubtitle(response: TimelineResponse): string {
  const season = SEASON_LABEL[response.season];
  return `시뮬레이션 · ${season} ${dayTypeLabel(response.day, response.is_holiday)}`;
}

/**
 * 할인이 어떤 날에 걸리는지. 배너 아래 한 줄로 쓴다.
 * 계절은 응답에서 오고, 요일 조건은 요금제 규칙이라 고정 문구다.
 */
export function discountScopeLabel(response: TimelineResponse): string {
  return `${SEASON_LABEL[response.season]} 토·일·공휴일`;
}

/** 공용 급속 단가의 상한. 백엔드 schemas.MAX_PRICE_PER_KWH와 같다. */
const MAX_PUBLIC_BASE_PRICE = 10_000;

/**
 * 공용 급속 단가 칸의 글자 → 보낼 수 있는 단가, 못 보내면 null.
 *
 * Number("")는 0이라 그냥 쓰면 빈 칸이 "0원"으로 나간다. 백엔드가 받지 않을 값(0 이하,
 * 상한 초과)도 여기서 걸러 null로 둔다 — 그러면 화면은 단가 없이 부르고, 백엔드가
 * "충전기에 적힌 요금을 넣어 달라"고 말해 준다. 틀린 숫자를 보내 받는 422보다 그 문장이 낫다.
 */
export function parsePublicBasePrice(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0 || value > MAX_PUBLIC_BASE_PRICE) return null;
  return value;
}

/**
 * "이 날짜로 충전 시간 추천받기"의 주소.
 *
 * 공용 급속은 단가가 없으면 추천도 못 하니, 여기서 넣은 단가를 같이 넘긴다 —
 * 추천 화면에서 같은 숫자를 또 치게 하지 않는다. 다른 방식에는 쓸모없는 값이라 싣지 않는다.
 */
export function recommendHref(day: string, mode: Mode, publicBasePrice: number | null): string {
  const params = new URLSearchParams({ day, mode });
  if (mode === "public_fast" && publicBasePrice !== null) {
    params.set("public_base_price", String(publicBasePrice));
  }
  return `/recommend?${params.toString()}`;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

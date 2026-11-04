import type { BandKey } from "@/components/chart/bands";
import { bandKeyOf } from "@/components/chart/bands";
import type { HourPrice } from "@/lib/api/types";

/**
 * 홈 '오늘 요금' 판이 응답에서 뽑는 값. 렌더링 없이 테스트하려고 컴포넌트 밖에 둔다.
 */

const EPSILON = 1e-6;

/** 지금 KST 몇 시인지 (0–23). 브라우저 표준시와 무관하게 서비스의 시계는 한국이다. */
export function hourInSeoul(now: Date = new Date()): number {
  const hour = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    hourCycle: "h23",
  }).format(now);
  return Number(hour) % 24;
}

export type HourRun = { start: number; end: number };

/**
 * 조건에 맞는 시각들을 이어진 구간으로 묶는다. 끝이 자정을 넘는 구간(22–24시 + 0–8시)은
 * 하나로 이어 붙인다 — "22시–08시"를 "0시–08시, 22시–24시"로 쪼개 말하면 읽는 사람이 다시 붙여야 한다.
 * end는 그 구간이 끝나는 시각(마지막 시각 + 1)이다.
 */
export function hourRuns(hours: number[]): HourRun[] {
  const set = new Set(hours);
  if (set.size === 0) return [];
  if (set.size === 24) return [{ start: 0, end: 24 }];

  const runs: HourRun[] = [];
  for (let hour = 0; hour < 24; hour += 1) {
    if (!set.has(hour)) continue;
    const last = runs.at(-1);
    if (last && last.end === hour) last.end = hour + 1;
    else runs.push({ start: hour, end: hour + 1 });
  }

  const first = runs[0];
  const last = runs.at(-1)!;
  if (runs.length > 1 && first.start === 0 && last.end === 24) {
    runs.pop();
    runs[0] = { start: last.start, end: first.end };
  }
  return runs;
}

/** "22시–08시" · "11시–15시" */
export function formatRun(run: HourRun): string {
  const pad = (hour: number) => String(hour % 24).padStart(2, "0");
  return `${pad(run.start)}시–${pad(run.end)}시`;
}

export type TodaySummary = {
  cells: { hour: number; bandKey: BandKey; price: number }[];
  minPrice: number;
  maxPrice: number;
  cheapest: HourRun[];
  priciest: HourRun[];
  /** 가장 비싼 시간 단가 ÷ 가장 싼 시간 단가 */
  ratio: number;
};

export function summarizeDay(hours: HourPrice[]): TodaySummary | null {
  if (hours.length === 0) return null;
  const prices = hours.map((entry) => entry.price_per_kwh);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const pick = (target: number) =>
    hours.filter((entry) => Math.abs(entry.price_per_kwh - target) < EPSILON).map((entry) => entry.hour);

  return {
    cells: hours.map((entry) => ({
      hour: entry.hour,
      bandKey: bandKeyOf(entry.band, entry.discounted),
      price: entry.price_per_kwh,
    })),
    minPrice,
    maxPrice,
    cheapest: hourRuns(pick(minPrice)),
    priciest: hourRuns(pick(maxPrice)),
    ratio: minPrice > 0 ? maxPrice / minPrice : 1,
  };
}

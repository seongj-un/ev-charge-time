import { bandKeyOf, BAND_KEY_LONG_LABEL, type BandKey } from "@/components/chart/bands";
import type { PriceColumn } from "@/components/chart/PriceBarChart";
import type { TimelineResponse } from "@/lib/api/types";
import { parseKstWallClock } from "@/lib/format";

/**
 * 추천 결과 차트의 x축을 만든다.
 *
 * 하루 단가 화면과 달리 여기 축은 0–23시가 아니다. 사용자가 넣은 "시작 가능 시각"부터
 * "완료 시각"까지가 축이고, 그건 대개 자정을 넘는다 (디자인: 18시 → 다음날 08시).
 * 그래서 timeline을 하루치만 받아서는 축을 채울 수 없고, 축이 걸친 날짜마다 받아
 * 이어 붙여야 한다.
 *
 * 이어 붙일 때 "둘째 날도 첫째 날과 같겠지" 하고 첫째 날을 두 번 쓰면 안 된다.
 * 계절·휴일·주말 할인이 날짜마다 달라서, 금요일 밤 요금표로 토요일 새벽을 그리면
 * 할인 구간이 통째로 사라진다.
 */

/**
 * 축이 24시간을 넘지 않게 자르는 이유:
 * PriceBarChart의 마커는 `marker.hours.includes(column.hour)`로 맞춘다. 즉 0–23 시각만
 * 본다. 축이 25칸이 되는 순간 같은 시각이 두 번 나오고, "추천" 표시가 충전하지도 않는
 * 막대 위에도 얹힌다. 그건 금액을 주장하는 화면에서 그냥 틀린 그림이다.
 */
const MAX_AXIS_HOURS = 24;

const MS_PER_DAY = 86_400_000;

export type Axis = {
  /** 에포크 기준 절대 시각 번호. 날짜를 넘어가도 단조 증가해서 날짜 계산이 필요 없다. */
  startIndex: number;
  /** 축의 칸 수 */
  length: number;
  /** 이 축을 채우려면 받아야 하는 날짜들 ("YYYY-MM-DD") */
  days: string[];
  /** 첫 칸의 시각 (0–23) */
  startHour: number;
  /** 마지막 칸의 시각 (0–23) */
  endHour: number;
  /** 마지막 칸이 첫 칸보다 며칠 뒤인지. 0이면 같은 날, 1이면 다음날 */
  dayOffset: number;
};

type AxisInput = {
  /** datetime-local 또는 ISO. 표준시는 붙어 있어도 무시한다 (벽시계 값만 읽는다) */
  earliestStart: string;
  deadline: string;
  /** 추천 구간. 창을 자를 때 추천이 밖으로 밀려나지 않게 하는 데만 쓴다 */
  bestStart?: string;
  bestEnd?: string;
};

export function buildAxis({
  earliestStart,
  deadline,
  bestStart,
  bestEnd,
}: AxisInput): Axis | null {
  let startIndex = hourIndexOf(earliestStart);
  const lastIndex = endHourIndexOf(deadline);

  // 완료가 시작보다 앞서면 그릴 축이 없다. 여기서 막지 않으면 빈 배열이 차트까지 내려가
  // "막대가 안 보이는데 왜죠" 가 된다.
  if (lastIndex < startIndex) return null;

  // 추천 구간이 24시간 창 밖이면 창을 추천 쪽으로 민다. 축은 요금을 보여주는 그림이고,
  // 그 그림에 추천이 안 들어 있으면 아무 설명도 못 한다.
  if (bestStart && bestEnd) {
    const bestEndIndex = endHourIndexOf(bestEnd);
    if (bestEndIndex > startIndex + MAX_AXIS_HOURS - 1) {
      startIndex = hourIndexOf(bestStart);
    }
  }

  const length = Math.min(lastIndex - startIndex + 1, MAX_AXIS_HOURS);
  const endIndex = startIndex + length - 1;

  return {
    startIndex,
    length,
    days: daysBetweenIndexes(startIndex, endIndex),
    startHour: hourOfIndex(startIndex),
    endHour: hourOfIndex(endIndex),
    dayOffset: dayOfIndex(endIndex) - dayOfIndex(startIndex),
  };
}

/**
 * 날짜별 timeline을 축 순서대로 이어 붙여 차트 컬럼을 만든다.
 *
 * 받지 못한 날짜의 칸은 넣지 않는다 (빈 막대를 0원처럼 그리면 그게 제일 나쁜 거짓말이다).
 */
export function buildColumns(axis: Axis, timelines: TimelineResponse[]): PriceColumn[] {
  const byDay = new Map(timelines.map((timeline) => [timeline.day, timeline]));
  const columns: PriceColumn[] = [];

  for (let offset = 0; offset < axis.length; offset += 1) {
    const index = axis.startIndex + offset;
    const timeline = byDay.get(dayStringOfIndex(index));
    if (!timeline) continue;

    const hour = hourOfIndex(index);
    const slot = timeline.hours.find((item) => item.hour === hour);
    if (!slot) continue;

    columns.push({
      hour,
      bandKey: bandKeyOf(slot.band, slot.discounted),
      pricePerKwh: slot.price_per_kwh,
    });
  }

  return columns;
}

/** "18시 → 다음날 08시". 끝은 마지막 막대가 아니라 축이 닫히는 시각이다. */
export function axisRangeLabel(axis: Axis): string {
  const exclusiveEnd = axis.endHour + 1;
  const endHour = exclusiveEnd % 24;
  const dayOffset = axis.dayOffset + (exclusiveEnd === 24 ? 1 : 0);
  const dayWord = dayOffset === 0 ? "" : dayOffset === 1 ? "다음날 " : `${dayOffset}일 뒤 `;
  return `${pad2(axis.startHour)}시 → ${dayWord}${pad2(endHour)}시`;
}

/**
 * 어떤 구간이 어느 부하구간에 걸쳤는지 한 마디로. 검정 카드의 배지와
 * "지금 바로" 카드의 설명이 같은 판단을 쓰도록 한 곳에 둔다.
 *
 * 여러 구간에 걸쳤는데 제일 많은 것 하나만 말하면 실제와 다르다 — "위주"를 붙인다.
 */
export function bandSummary(columns: PriceColumn[], hours: number[]): string | null {
  const counts = new Map<BandKey, number>();
  for (const column of columns) {
    if (!hours.includes(column.hour)) continue;
    counts.set(column.bandKey, (counts.get(column.bandKey) ?? 0) + 1);
  }
  if (counts.size === 0) return null;

  const [topKey] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  const label = BAND_KEY_LONG_LABEL[topKey];
  return counts.size === 1 ? label : `${label} 위주`;
}

/** 시각이 든 칸의 절대 번호. 분은 버린다 — 18:40에 시작해도 18시 막대부터다. */
function hourIndexOf(iso: string): number {
  const wall = parseKstWallClock(iso);
  return dayNumber(wall) * 24 + wall.hour;
}

/**
 * 끝나는 쪽의 마지막 칸 번호. 정시에 끝나면 그 시각 막대는 쓰지 않았다
 * (charging.ts의 coveredHours와 같은 규칙이어야 마커와 축이 어긋나지 않는다).
 */
function endHourIndexOf(iso: string): number {
  const wall = parseKstWallClock(iso);
  const base = dayNumber(wall) * 24 + wall.hour;
  return wall.minute > 0 ? base : base - 1;
}

function dayNumber(wall: { year: number; month: number; day: number }): number {
  return Math.floor(Date.UTC(wall.year, wall.month - 1, wall.day) / MS_PER_DAY);
}

function dayOfIndex(index: number): number {
  return Math.floor(index / 24);
}

function hourOfIndex(index: number): number {
  return index - dayOfIndex(index) * 24;
}

/** 절대 번호 → "YYYY-MM-DD". UTC로만 다뤄서 브라우저 표준시가 끼어들 틈이 없다. */
function dayStringOfIndex(index: number): string {
  return new Date(dayOfIndex(index) * MS_PER_DAY).toISOString().slice(0, 10);
}

function daysBetweenIndexes(startIndex: number, endIndex: number): string[] {
  const days: string[] = [];
  for (let day = dayOfIndex(startIndex); day <= dayOfIndex(endIndex); day += 1) {
    days.push(new Date(day * MS_PER_DAY).toISOString().slice(0, 10));
  }
  return days;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

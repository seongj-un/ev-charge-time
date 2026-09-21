import { formatDuration, formatKoreanDate, parseKstWallClock } from "@/lib/format";

/**
 * 추천 계획을 사람 말로 옮기는 곳.
 *
 * "오늘 밤 시작 · 약 3시간 · 내일 08시 전 완료" 한 줄이 이 화면에서 제일 많이 읽힌다.
 * 상대 날짜의 기준을 `new Date()`로 잡지 않는 것이 중요하다. 실제 현재 시각을 기준으로
 * 삼으면 자정을 넘길 때마다 같은 링크가 다른 문장을 내고, 미래 날짜로 시연하면
 * "오늘"이 통째로 사라진다. 기준은 사용자가 넣은 "시작 가능 시각"의 날짜다.
 */

const MS_PER_DAY = 86_400_000;

/** 기준 날짜에서 본 상대 날짜말. 사흘 이상 벌어지면 그냥 날짜를 적는다. */
export function relativeDayWord(baseIso: string, targetIso: string): string {
  const gap = dayNumberOf(targetIso) - dayNumberOf(baseIso);
  if (gap === 0) return "오늘";
  if (gap === 1) return "내일";
  if (gap === 2) return "모레";
  return formatKoreanDate(targetIso);
}

/** 구간 길이(시간). 자정을 넘어도 날짜 차이를 더해 센다. */
export function durationHours(startIso: string, endIso: string): number {
  return (minutesOf(endIso) - minutesOf(startIso)) / 60;
}

/** 하루 중 어느 때인지. 22:00을 "밤"이라고 불러야 "오늘 밤 시작"이 된다. */
export function partOfDay(hour: number): string {
  if (hour < 6) return "새벽";
  if (hour < 11) return "아침";
  if (hour < 14) return "낮";
  if (hour < 18) return "오후";
  if (hour < 22) return "저녁";
  return "밤";
}

type PlanSentenceInput = {
  /** 상대 날짜말의 기준이자 사용자가 넣은 조건 */
  earliestStart: string;
  deadline: string;
  /** 추천 구간 (서버 값) */
  start: string;
  end: string;
};

/** "오늘 밤 시작 · 약 3시간 · 내일 08시 전 완료" */
export function planSummarySentence({
  earliestStart,
  deadline,
  start,
  end,
}: PlanSentenceInput): string {
  const startWall = parseKstWallClock(start);
  const deadlineWall = parseKstWallClock(deadline);

  const startPhrase = `${relativeDayWord(earliestStart, start)} ${partOfDay(startWall.hour)} 시작`;
  const durationPhrase = formatDuration(durationHours(start, end));
  const deadlinePhrase =
    `${relativeDayWord(earliestStart, deadline)} ` +
    `${String(deadlineWall.hour).padStart(2, "0")}시 전 완료`;

  return `${startPhrase} · ${durationPhrase} · ${deadlinePhrase}`;
}

/**
 * "계산 가정: 충전 출력 일정 · 연속 충전 · 기본요금 제외"
 *
 * 백엔드가 응답마다 assumptions를 실어 보내는 이유가 있다 — 이 금액이 어떤 전제 위에
 * 서 있는지 화면에 없으면, 읽는 사람은 그냥 "이 값이 내 요금"이라고 받아들인다.
 */
export function assumptionsSentence(assumptions: string[]): string | null {
  if (assumptions.length === 0) return null;
  return `계산 가정: ${assumptions.join(" · ")}`;
}

/**
 * 확인 전 요금 고지 문구.
 *
 * 백엔드가 주는 unverified_tariff_items는 `adders.climate_env_per_kwh`처럼 코드 안에서
 * 쓰는 키다. 그걸 그대로 문장에 이어 붙이면 아무도 읽지 않는 아홉 줄이 되고,
 * 안 읽히는 고지는 고지가 아니다. 그래서 읽는 사람이 알아야 할 것은 이 한 문장으로
 * 고정하고, 실제 항목 목록은 이 문장 아래 접어서 그대로 보여준다.
 */
export const UNVERIFIED_NOTICE =
  "시간대 구분과 부가 요금은 공식 요금표 확인 전 값입니다.";

function dayNumberOf(iso: string): number {
  const wall = parseKstWallClock(iso);
  return Math.floor(Date.UTC(wall.year, wall.month - 1, wall.day) / MS_PER_DAY);
}

function minutesOf(iso: string): number {
  const wall = parseKstWallClock(iso);
  return dayNumberOf(iso) * 24 * 60 + wall.hour * 60 + wall.minute;
}

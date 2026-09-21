import type { RecommendRequest, SavedPlan } from "@/lib/api/types";
import { formatKwh, parseKstWallClock } from "@/lib/format";

/**
 * 충전 기록 화면이 쓰는 순수 계산. 요청도 상태도 없어서 그대로 테스트된다.
 */

const MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/;

/** 주소창은 누구나 고친다. "YYYY-MM"이 아니면 쓰지 않는다. */
export function isMonth(value: string | null | undefined): value is string {
  return typeof value === "string" && MONTH_PATTERN.test(value);
}

/**
 * created_at이 속한 달.
 *
 * `new Date(created_at).getMonth()`를 쓰면 안 된다. 백엔드가 주는 값은 KST(+09:00)인데
 * Date로 만들면 브라우저·CI 표준시로 다시 읽혀, 10월 1일 새벽 기록이 9월로 분류된다.
 * ISO 문자열에 적힌 벽시계 값을 그대로 쓴다 (format.ts와 같은 이유).
 */
export function monthOf(iso: string): string {
  const { year, month } = parseKstWallClock(iso);
  return `${year}-${pad2(month)}`;
}

/** 사용자 시계 기준 이번 달. 브라우저에서만 불러야 한다 (hooks.ts의 useIsHydrated). */
export function currentMonth(now: Date): string {
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}`;
}

const OPTION_COUNT = 12;
/**
 * 앞으로 올 달도 보여준다.
 *
 * 월 기준이 **충전 날짜**라, 오늘 세운 계획은 대개 앞으로 충전할 것이다.
 * 과거만 주면 "오늘 저장한 다음 달 계획"을 고를 수가 없어서, 저장하고도 못 찾는다.
 */
const MONTHS_AHEAD = 2;

/**
 * 월 선택에 띄울 달들. 앞으로 2개월 + 이번 달 + 과거로 채워 12개.
 *
 * 고른 달이 그 12개 밖이면(오래된 링크를 받은 경우) 끼워 넣는다. 목록에 없는 값을
 * <select>에 물리면 브라우저가 멋대로 첫 항목을 고른 것처럼 보여서, 화면의 달과
 * 주소의 달이 달라진다.
 */
export function monthOptions(now: Date, selected: string): string[] {
  const months: string[] = [];
  for (let offset = MONTHS_AHEAD; offset > OPTION_COUNT * -1 + MONTHS_AHEAD; offset -= 1) {
    const date = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    months.push(currentMonth(date));
  }
  if (!months.includes(selected)) {
    months.push(selected);
    months.sort().reverse();
  }
  return months;
}

/** "2026년 10월" */
export function formatMonth(month: string): string {
  const matched = MONTH_PATTERN.exec(month);
  if (!matched) return month;
  return `${matched[1]}년 ${Number(matched[2])}월`;
}

/**
 * 기록 한 줄의 '차량' 칸. 이름과 조건을 **둘 다** 보여준다.
 *
 * 차량을 고른 뒤 폼의 값을 직접 고쳐 저장할 수 있다. 서버는 둘의 일치를 검사하지
 * 않고, 그게 맞다 — 그 차량을 기준으로 시작한 계획이니까. 다만 화면이 "출퇴근 차"라고만
 * 쓰면 사용자가 그 차의 제원 그대로 계산됐다고 읽는다. 77 kWh 차를 골라 58로 고쳐
 * 저장했는데 이름만 보이면, 나중에 그 기록을 잘못된 전제로 다시 읽게 된다.
 *
 * vehicle_name이 null인 것(직접 입력)은 정상값이라 조건만 남는다.
 */
export function vehicleLabel(plan: SavedPlan): string {
  const condition = conditionLabel(plan.request);
  const name = plan.vehicle_name?.trim();
  return name ? `${name} · ${condition}` : condition;
}

/** "70 kWh · 7 kW" */
export function conditionLabel(request: RecommendRequest): string {
  return `${formatKwh(request.battery_kwh)} · ${request.charger_kw} kW`;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

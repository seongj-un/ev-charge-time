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
 * 월 선택에 띄울 달들. 이번 달부터 과거로 12개.
 *
 * 고른 달이 그 12개 밖이면(오래된 링크를 받은 경우) 끼워 넣는다. 목록에 없는 값을
 * <select>에 물리면 브라우저가 멋대로 첫 항목을 고른 것처럼 보여서, 화면의 달과
 * 주소의 달이 달라진다.
 */
export function monthOptions(now: Date, selected: string): string[] {
  const months: string[] = [];
  for (let back = 0; back < OPTION_COUNT; back += 1) {
    const date = new Date(now.getFullYear(), now.getMonth() - back, 1);
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
 * 기록 한 줄의 '차량' 칸.
 *
 * ⚠️ 응답에 차량 이름이 없다. 디자인의 "출퇴근 차"를 그리려면 이름을 지어내거나
 * 차량 API와 조인해야 하는데, 지어내는 건 금액을 틀리게 적는 것과 같은 거짓말이고
 * 조인은 이번 범위가 아니다. 그래서 저장된 조건을 그대로 되읽어 준다.
 *
 * 백엔드가 `vehicle_name`(저장 시점 스냅샷, 직접 입력이면 null)을 넣기로 했다.
 * 그때 이 함수의 마지막 줄이 `plan.vehicle_name ?? conditionLabel(...)`이 된다 —
 * null이 정상값이라 조건 폴백은 그 뒤로도 계속 쓰인다.
 */
export function vehicleLabel(plan: SavedPlan): string {
  const condition = conditionLabel(plan.request);
  // 등록 차량으로 저장했는지는 request에 남아 있을 수 있다. 이름은 몰라도
  // "직접 입력이 아니라 내 차량으로 저장했다"는 사실까지 버릴 이유는 없다.
  const vehicleId = (plan.request as RecommendRequest & { vehicle_id?: string }).vehicle_id;
  return vehicleId ? `내 차량 · ${condition}` : condition;
}

/** "70 kWh · 7 kW" */
export function conditionLabel(request: RecommendRequest): string {
  return `${formatKwh(request.battery_kwh)} · ${request.charger_kw} kW`;
}

/** 그 달에 저장된 기록만 남긴다. */
export function filterByMonth(items: SavedPlan[], month: string): SavedPlan[] {
  return items.filter((item) => monthOf(item.created_at) === month);
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

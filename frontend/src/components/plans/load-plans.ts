import { fetchPlans } from "@/lib/api/endpoints";
import type { SavedPlan } from "@/lib/api/types";

/**
 * "그 달의 기록 한 페이지"를 가져오는 단 하나의 창구.
 *
 * 필터도 정렬도 서버가 한다. month는 **충전 날짜**(charge_start) 기준이고
 * 정렬도 같은 기준 내림차순이다 (API 명세서 7-3). 프론트에서 거르던 시절에는
 * "그 달 기록이 다음 커서 페이지에 있어 안 보이는" 구멍이 있었는데, 그건
 * 화면에 한계를 적어 덮을 문제가 아니라 API가 가져야 할 필터였다.
 */

/** limit은 1~100이어야 한다. 범위 밖이면 422. */
export const PAGE_SIZE = 20;

export type PlanPage = {
  items: SavedPlan[];
  nextCursor: string | null;
};

export async function loadPlanPage(params: {
  month: string;
  cursor?: string;
}): Promise<PlanPage> {
  const page = await fetchPlans({
    month: params.month,
    limit: PAGE_SIZE,
    cursor: params.cursor,
  });
  return { items: page.items, nextCursor: page.next_cursor };
}

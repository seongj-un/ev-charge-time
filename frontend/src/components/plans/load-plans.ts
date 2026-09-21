import { fetchPlans } from "@/lib/api/endpoints";
import type { SavedPlan } from "@/lib/api/types";

import { filterByMonth } from "./plan-view";

/**
 * "그 달의 기록 한 페이지"를 가져오는 단 하나의 창구.
 *
 * ⚠️ 목록 API에는 아직 month 필터가 없다 (백엔드가 넣기로 했고 아직 배포 전).
 * FastAPI는 모르는 쿼리 파라미터를 **조용히 무시**하므로, 미리 month를 실어 보내면
 * 걸러진 것처럼 보이는 전체 목록이 돌아온다. 화면이 조용히 거짓말을 하는 것보다
 * 프론트에서 거르고 한계를 화면에 밝히는 편이 낫다. 그래서 month는 이 함수 밖으로
 * 나가지 않는다.
 *
 * 백엔드에 month가 생기면 고칠 곳은 이 함수 본문 한 군데다:
 *   const page = await fetchPlans({ month, limit: PAGE_SIZE, cursor });
 *   return { items: page.items, fetched: page.items.length, nextCursor: page.next_cursor };
 * 화면은 이미 "월 + 커서"로만 목록을 요청하고 있어서 그대로 둔다.
 */

/** ⚠️ limit=0을 보내면 지금 백엔드가 500을 낸다. 0이 될 수 없는 상수로 고정한다. */
export const PAGE_SIZE = 20;

export type PlanPage = {
  /** 그 달의 기록만 (최신순) */
  items: SavedPlan[];
  /** 서버에서 실제로 받아 온 개수. 프론트 필터로 몇 건이 걸러졌는지 알려면 필요하다. */
  fetched: number;
  nextCursor: string | null;
};

export async function loadPlanPage(params: {
  month: string;
  cursor?: string;
}): Promise<PlanPage> {
  const page = await fetchPlans({ limit: PAGE_SIZE, cursor: params.cursor });
  return {
    items: filterByMonth(page.items, params.month),
    fetched: page.items.length,
    nextCursor: page.next_cursor,
  };
}

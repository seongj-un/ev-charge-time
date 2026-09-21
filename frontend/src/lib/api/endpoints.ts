import { apiGet, apiPost } from "./client";
import type {
  HealthResponse,
  Mode,
  RecommendRequest,
  RecommendResponse,
  TimelineResponse,
} from "./types";

/** GET /health — F-08. 공식 확인이 안 끝난 요금 항목 목록을 함께 준다. */
export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}

/** GET /api/timeline — F-05·F-06. day는 임의 날짜 가능 (시뮬레이션). */
export function fetchTimeline(params: {
  day: string;
  mode?: Mode;
  publicBasePrice?: number;
}): Promise<TimelineResponse> {
  return apiGet<TimelineResponse>("/api/timeline", {
    day: params.day,
    mode: params.mode,
    public_base_price: params.publicBasePrice,
  });
}

/** POST /api/recommend — F-01·F-03·F-04. 게스트도 호출할 수 있다. */
export function fetchRecommendation(
  request: RecommendRequest,
): Promise<RecommendResponse> {
  return apiPost<RecommendResponse>("/api/recommend", request);
}

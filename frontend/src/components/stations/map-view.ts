import type { Station } from "@/lib/api/types";

import { statusView } from "./station-view";

/**
 * 지도에 찍을 점.
 *
 * 목록과 같은 사실을 말해야 한다. 목록의 "사용 가능만" 필터는 뜻을 아는 코드만
 * 세는데, 지도가 모르는 코드를 초록으로 찍으면 같은 화면이 두 가지 말을 한다.
 */
export type MapPoint = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  /** 뜻을 아는 '사용 가능' 충전기가 하나라도 있는지 */
  available: boolean;
};

/** 지구 위에 있을 수 있는 좌표인지. */
function plottable(lat: number, lng: number): boolean {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return false;
  /*
   * 0,0은 기니만 앞바다다. 좌표가 빈 곳을 그대로 찍으면 지도가 아프리카까지
   * 축소되고 한국 쪽 점이 전부 한 픽셀로 뭉친다 — 한 곳 때문에 화면 전체가
   * 못 쓰게 된다. 실데이터에는 없지만 상태 코드·출력에서 이미 한 번씩 당했다.
   */
  return !(lat === 0 && lng === 0);
}

export function toMapPoints(stations: Station[]): MapPoint[] {
  return stations
    .filter((item) => plottable(item.lat, item.lng))
    .map((item) => ({
      id: item.station_id,
      name: item.name,
      lat: item.lat,
      lng: item.lng,
      available: (item.chargers ?? []).some(
        (charger) => statusView(charger.status).available,
      ),
    }));
}

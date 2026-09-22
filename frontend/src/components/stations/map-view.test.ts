import { describe, expect, test } from "vitest";

import { toMapPoints } from "./map-view";
import { FAST_AVAILABLE, SLOW_CHARGING, UNKNOWN_STATUS, station } from "./test-support";

/*
 * 지도에 찍을 점.
 *
 * 목록과 같은 사실을 말해야 한다. 목록은 "사용 가능만" 필터가 뜻을 아는 코드만
 * 세는데 지도가 모르는 코드를 초록으로 찍으면, 같은 화면이 두 가지 말을 한다.
 */
describe("지도 점", () => {
  test("충전소마다 점 하나를 만든다", () => {
    const points = toMapPoints([
      station({ station_id: "A", name: "가람프라자", lat: 35.0191, lng: 126.7921 }),
      station({ station_id: "B", name: "나주금화타워", lat: 35.02, lng: 126.79 }),
    ]);
    expect(points.map((p) => p.id)).toEqual(["A", "B"]);
    expect(points[0].name).toBe("가람프라자");
    expect(points[0].lat).toBe(35.0191);
  });

  /*
   * 0,0은 기니만 앞바다다. 좌표가 비면 지도가 아프리카까지 축소돼서 한국 쪽
   * 점이 전부 한 픽셀로 뭉친다 — 한 곳 때문에 화면 전체가 못 쓰게 된다.
   */
  test("0,0은 찍지 않는다", () => {
    expect(toMapPoints([station({ station_id: "A", lat: 0, lng: 0 })])).toHaveLength(0);
  });

  test("숫자가 아닌 좌표는 찍지 않는다", () => {
    expect(
      toMapPoints([station({ station_id: "A", lat: Number.NaN, lng: 126.79 })]),
    ).toHaveLength(0);
  });

  test("범위를 벗어난 좌표는 찍지 않는다", () => {
    // 위도는 ±90, 경도는 ±180을 넘을 수 없다.
    expect(toMapPoints([station({ station_id: "A", lat: 935, lng: 126.79 })])).toHaveLength(0);
  });

  describe("사용 가능 표시", () => {
    test("뜻을 아는 사용 가능 코드가 하나라도 있으면 사용 가능이다", () => {
      const points = toMapPoints([
        station({ station_id: "A", lat: 35.01, lng: 126.79, chargers: [FAST_AVAILABLE] }),
      ]);
      expect(points[0].available).toBe(true);
    });

    test("충전 중만 있으면 사용 가능이 아니다", () => {
      const points = toMapPoints([
        station({ station_id: "A", lat: 35.01, lng: 126.79, chargers: [SLOW_CHARGING] }),
      ]);
      expect(points[0].available).toBe(false);
    });

    /* 목록 필터와 같은 원칙이다 — 모르는 코드를 사용 가능으로 넘겨짚지 않는다. */
    test("모르는 상태 코드는 사용 가능으로 세지 않는다", () => {
      const points = toMapPoints([
        station({ station_id: "A", lat: 35.01, lng: 126.79, chargers: [UNKNOWN_STATUS] }),
      ]);
      expect(points[0].available).toBe(false);
    });

    /* null은 "충전기가 0대"가 아니라 "아직 못 불러왔다"다 (API 명세서 7-4). */
    test("충전기를 못 불러온 곳도 지도에는 찍되 사용 가능이라 하지 않는다", () => {
      const points = toMapPoints([
        station({ station_id: "A", lat: 35.01, lng: 126.79, chargers: null }),
      ]);
      expect(points).toHaveLength(1);
      expect(points[0].available).toBe(false);
    });
  });

  test("빈 목록은 빈 배열이다", () => {
    expect(toMapPoints([])).toEqual([]);
  });
});

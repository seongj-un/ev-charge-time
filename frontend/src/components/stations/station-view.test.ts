import { describe, expect, test } from "vitest";

import {
  NAME_MISSING,
  chargerTypeLabel,
  filterStations,
  formatCapacity,
  formatDistance,
  latestStatusUpdate,
  metaLine,
  statusUpdatedLabel,
  statusView,
} from "./station-view";
import { FAST_AVAILABLE, SLOW_CHARGING, UNKNOWN_STATUS, station } from "./test-support";

describe("충전기 상태 코드", () => {
  test("뜻이 코드에 적혀 있는 값만 우리말로 옮긴다", () => {
    expect(statusView("available")).toEqual({
      label: "사용 가능",
      tone: "ok",
      known: true,
      available: true,
    });
    expect(statusView("charging").label).toBe("충전 중");
    expect(statusView("maintenance").label).toBe("점검 중");
  });

  test("대소문자와 공백은 무시한다", () => {
    expect(statusView("  CHARGING ").label).toBe("충전 중");
  });

  /**
   * 이 테스트가 이 화면에서 제일 중요하다.
   *
   * 명세 2-4가 "상태 코드 매핑은 원본 API 문서 확인 후 확정"으로 남아 있다.
   * 모르는 코드를 '사용 가능'으로 넘겨짚으면 사용자는 없는 자리를 찾아 차를 몬다.
   */
  test("모르는 코드는 지어내지 않고 코드를 그대로 보여준다", () => {
    expect(statusView("2")).toEqual({
      label: "2",
      tone: "off",
      known: false,
      available: false,
    });
    expect(statusView("STAT_9").label).toBe("STAT_9");
  });

  test("빈 코드는 빈 배지가 아니라 모른다고 말한다", () => {
    expect(statusView("").label).toBe("상태 없음");
    expect(statusView("").available).toBe(false);
  });
});

describe("충전기 종류", () => {
  test("자기 뜻을 적어 보낸 값만 옮기고 나머지는 원문을 남긴다", () => {
    expect(chargerTypeLabel("fast")).toBe("급속");
    expect(chargerTypeLabel("slow")).toBe("완속");
    expect(chargerTypeLabel("DC_CHAdeMO")).toBe("DC_CHAdeMO");
  });
});

describe("숫자 표기", () => {
  test("1km 미만은 미터로, 그 위는 소수 첫째 자리 킬로미터로 쓴다", () => {
    expect(formatDistance(320)).toBe("320 m");
    expect(formatDistance(1240)).toBe("1.2 km");
  });

  test("거리를 모르면 빈 문자열이다 — 0 km라고 단정하지 않는다", () => {
    expect(formatDistance(null)).toBe("");
  });

  test("용량은 소수점이 필요 없으면 붙이지 않는다", () => {
    expect(formatCapacity(100)).toBe("100");
    expect(formatCapacity(3.5)).toBe("3.5");
  });
});

describe("메타 줄", () => {
  test("null과 빈 칸은 빼고 가운뎃점으로 잇는다", () => {
    expect(metaLine(["서울 중구", null, "한국전력", "  "])).toBe("서울 중구 · 한국전력");
  });

  test("전부 비어 있으면 빈 문자열이다", () => {
    expect(metaLine([null, null])).toBe("");
  });
});

describe("필터", () => {
  const fastOnly = station({ station_id: "A", chargers: [FAST_AVAILABLE] });
  const slowOnly = station({ station_id: "B", chargers: [SLOW_CHARGING] });
  const unknownOnly = station({ station_id: "C", chargers: [UNKNOWN_STATUS] });

  test("전체는 아무것도 걸러내지 않는다", () => {
    const all = [fastOnly, slowOnly, unknownOnly];
    expect(filterStations(all, { type: "all", availableOnly: false })).toHaveLength(3);
  });

  test("급속은 급속 충전기가 있는 곳만 남긴다", () => {
    const kept = filterStations([fastOnly, slowOnly], { type: "fast", availableOnly: false });
    expect(kept.map((item) => item.station_id)).toEqual(["A"]);
  });

  /** 모르는 코드를 '사용 가능'으로 세면 필터가 거짓말이 된다. */
  test("사용 가능만은 확인된 코드만 남기고 모르는 코드는 뺀다", () => {
    const kept = filterStations([fastOnly, slowOnly, unknownOnly], {
      type: "all",
      availableOnly: true,
    });
    expect(kept.map((item) => item.station_id)).toEqual(["A"]);
  });

  test("종류와 상태 조건은 같은 충전기 한 대가 동시에 만족해야 한다", () => {
    const mixed = station({
      station_id: "D",
      // 급속은 충전 중이고, 사용 가능한 건 완속뿐이다 — '급속 + 사용 가능만'에 걸리면 안 된다.
      chargers: [
        { ...FAST_AVAILABLE, status: "charging" },
        { ...SLOW_CHARGING, status: "available" },
      ],
    });
    expect(filterStations([mixed], { type: "fast", availableOnly: true })).toHaveLength(0);
    expect(filterStations([mixed], { type: "slow", availableOnly: true })).toHaveLength(1);
  });
});

describe("상태 갱신 시각", () => {
  test("충전기들 중 가장 최근 값을 고른다", () => {
    const latest = latestStatusUpdate([
      station({ chargers: [SLOW_CHARGING, FAST_AVAILABLE] }),
    ]);
    expect(latest).toBe("2026-09-21T22:10:00+09:00");
  });

  test("갱신 시각이 하나도 없으면 null이다", () => {
    expect(latestStatusUpdate([station({ chargers: [UNKNOWN_STATUS] })])).toBeNull();
    expect(latestStatusUpdate([station({ chargers: null })])).toBeNull();
  });

  test("시각이 없으면 없다고 적는다 — 지금 시각을 적지 않는다", () => {
    expect(statusUpdatedLabel(null)).toBe("상태 갱신 시각 없음");
    expect(statusUpdatedLabel("2026-09-21T22:10:00+09:00")).toBe("상태 갱신 22:10");
  });

  test("읽을 수 없는 시각이 와도 화면을 세우지 않는다", () => {
    expect(statusUpdatedLabel("뭔가 이상한 값")).toBe("상태 갱신 시각 없음");
  });
});

test("이름이 없는 즐겨찾기에 쓸 문구가 한 곳에만 있다", () => {
  expect(NAME_MISSING).toBe("이름을 아직 불러오지 못했어요");
});

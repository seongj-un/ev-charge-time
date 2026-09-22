import { describe, expect, test } from "vitest";

import {
  NAME_MISSING,
  speedLabel,
  speedOf,
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

/*
 * 타입 코드로 급속/완속을 가를 수 없다.
 *
 * 실데이터(전남광주 32,835대)에서 type=04가 7~350 kW에 걸쳐 있고
 * 그중 137대는 50 kW 미만이다. 타입으로 가르면 수백 대가 틀린다.
 * capacity_kw는 API가 주는 실측값이라 그럴 여지가 없다.
 */
describe("충전 속도", () => {
  test("50 kW를 경계로 가른다", () => {
    // 실데이터에서 41~49 kW는 한 대도 없다 — 40과 50 사이가 비어 있다.
    expect(speedOf(50)).toBe("fast");
    expect(speedOf(100)).toBe("fast");
    expect(speedOf(40)).toBe("slow");
    expect(speedOf(7)).toBe("slow");
  });

  /* 0 kW가 20대 실제로 있다. 완속이라 말하면 없는 사실을 지어내는 것이다. */
  test("출력을 모르면 속도도 단정하지 않는다", () => {
    expect(speedOf(0)).toBe("unknown");
  });

  test("속도 라벨은 출력을 모를 때 지어내지 않는다", () => {
    expect(speedLabel(100)).toBe("급속");
    expect(speedLabel(7)).toBe("완속");
    expect(speedLabel(0)).toBe("출력 정보 없음");
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
  // 실제 API가 주는 모양: 타입은 "02"·"04" 같은 숫자, 속도는 kW가 말해 준다.
  const fastOnly = station({ station_id: "A", chargers: [FAST_AVAILABLE] });
  const slowOnly = station({ station_id: "B", chargers: [SLOW_CHARGING] });
  const unknownOnly = station({ station_id: "C", chargers: [UNKNOWN_STATUS] });

  test("전체는 아무것도 걸러내지 않는다", () => {
    const all = [fastOnly, slowOnly, unknownOnly];
    expect(filterStations(all, { type: "all", availableOnly: false })).toHaveLength(3);
  });

  test("급속은 50 kW 이상 충전기가 있는 곳만 남긴다", () => {
    const kept = filterStations([fastOnly, slowOnly], { type: "fast", availableOnly: false });
    expect(kept.map((item) => item.station_id)).toEqual(["A"]);
  });

  test("완속은 50 kW 미만만 남긴다", () => {
    const kept = filterStations([fastOnly, slowOnly], { type: "slow", availableOnly: false });
    expect(kept.map((item) => item.station_id)).toEqual(["B"]);
  });

  /*
   * 타입 코드는 속도를 정하지 못한다. type=04가 7 kW일 수도 있고
   * type=02가 50 kW일 수도 있다 — 둘 다 실데이터에 있는 조합이다.
   */
  test("타입 코드가 아니라 출력으로 가른다", () => {
    const misleading = station({
      station_id: "D",
      chargers: [{ ...FAST_AVAILABLE, type: "04", capacity_kw: 7 }],
    });
    expect(filterStations([misleading], { type: "fast", availableOnly: false })).toHaveLength(0);
    expect(filterStations([misleading], { type: "slow", availableOnly: false })).toHaveLength(1);
  });

  test("출력을 모르는 충전기는 급속에도 완속에도 안 끼운다", () => {
    const noCapacity = station({
      station_id: "E",
      chargers: [{ ...FAST_AVAILABLE, capacity_kw: 0 }],
    });
    expect(filterStations([noCapacity], { type: "fast", availableOnly: false })).toHaveLength(0);
    expect(filterStations([noCapacity], { type: "slow", availableOnly: false })).toHaveLength(0);
    expect(filterStations([noCapacity], { type: "all", availableOnly: false })).toHaveLength(1);
  });

  /** 모르는 코드를 '사용 가능'으로 세면 필터가 거짓말이 된다. */
  test("사용 가능만은 확인된 코드만 남긴다", () => {
    const kept = filterStations([fastOnly, slowOnly, unknownOnly], {
      type: "all",
      availableOnly: true,
    });
    expect(kept.map((item) => item.station_id)).toEqual(["A"]);
  });

  test("속도와 상태 조건은 같은 충전기 한 대가 동시에 만족해야 한다", () => {
    const mixed = station({
      station_id: "F",
      // 급속은 충전 중이고, 비어 있는 건 완속뿐이다.
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

import { describe, expect, test } from "vitest";

import {
  AREAS,
  DEFAULT_AREA,
  geoBlockMessage,
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

/*
 * 기준은 한국환경공단 활용가이드 v1.25(2026-07-01) 3.2절 stat 공통코드다.
 * 원본: docs/sources/한국환경공단_전기자동차 충전소 정보_OpenAPI활용가이드_v1.25.docx
 */
describe("충전기 상태 코드", () => {
  test("공식 코드표의 코드를 우리말로 옮긴다", () => {
    expect(statusView("2")).toEqual({ label: "사용 가능", tone: "ok", known: true, available: true });
    expect(statusView("3")).toEqual({ label: "충전 중", tone: "warn", known: true, available: false });
    expect(statusView("6")).toEqual({ label: "예약 중", tone: "warn", known: true, available: false });
    expect(statusView("5")).toEqual({ label: "점검 중", tone: "off", known: true, available: false });
    expect(statusView("4")).toEqual({ label: "운영 중지", tone: "off", known: true, available: false });
    expect(statusView("1")).toEqual({ label: "통신 이상", tone: "off", known: true, available: false });
  });

  /*
   * 0(알수없음)과 9(상태미확인)는 뜻을 아는 코드다 — 그 뜻이 "모른다"일 뿐이다.
   * 실데이터에 9가 5% 넘게 있어서, 이걸 모르는 코드로 치면 화면이 늘
   * "확정되지 않은 코드가 있다"고 말하게 된다.
   */
  test("알수없음(0)과 상태미확인(9)은 상태를 모른다고 말한다", () => {
    expect(statusView("0")).toEqual({ label: "알 수 없음", tone: "off", known: true, available: false });
    expect(statusView("9")).toEqual({ label: "상태 미확인", tone: "off", known: true, available: false });
  });

  /**
   * 이 테스트가 이 화면에서 제일 중요하다.
   *
   * '사용 가능'을 하나라도 잘못 세면 사용자는 없는 자리를 찾아 차를 몬다.
   */
  test("사용 가능은 충전대기(2) 하나뿐이다", () => {
    const official = ["0", "1", "2", "3", "4", "5", "6", "9"];
    expect(official.filter((code) => statusView(code).available)).toEqual(["2"]);
  });

  test("앞뒤 공백은 무시한다", () => {
    expect(statusView(" 3 ").label).toBe("충전 중");
  });

  test("코드표에 없는 코드는 지어내지 않고 코드를 그대로 보여준다", () => {
    expect(statusView("7")).toEqual({ label: "7", tone: "off", known: false, available: false });
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
        { ...FAST_AVAILABLE, status: "3" },
        { ...SLOW_CHARGING, status: "2" },
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

/*
 * 위치를 못 얻었을 때 고를 지역.
 *
 * 화면이 좌표 하나에 걸려 있으면 안 된다 — 사이트 권한이 "허용"이어도 OS가 막으면
 * getCurrentPosition이 PERMISSION_DENIED로 떨어진다(실제로 그렇게 막혔다).
 * 그때 빠져나갈 길이 없으면 시연 도중 화면이 죽는다.
 *
 * 여기 좌표는 지어낸 값이 아니라 **실제 API로 결과가 나오는 것만** 남긴 것이다
 * (빛가람 158곳 · 광주 320곳 · 목포 137곳 · 여수 127곳 · 순천 96곳, 반경 2km).
 * 충전소를 흉내 내는 상수가 아니라 조회 기준점이라 이 파일에 둔다.
 */
describe("지역 기준점", () => {
  test("기본값은 빛가람혁신도시다 — 대회장이고 데이터가 있는 곳이다", () => {
    expect(DEFAULT_AREA.name).toBe("빛가람혁신도시");
    expect(AREAS[0]).toBe(DEFAULT_AREA);
  });

  test("id가 겹치지 않는다", () => {
    const ids = AREAS.map((area) => area.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  /*
   * 캐시가 전남·광주만 담고 있다. 서울 좌표를 하나 끼워 넣으면 그 지역을 고른
   * 사람에게는 빈 목록이 나오고, 화면은 "충전소가 없다"고 거짓말한다.
   * 그래서 경계를 테스트로 박아 둔다.
   */
  test("전부 수집된 지역(전남·광주) 안에 있다", () => {
    for (const area of AREAS) {
      expect(area.lat).toBeGreaterThan(34.0);
      expect(area.lat).toBeLessThan(35.5);
      expect(area.lng).toBeGreaterThan(125.8);
      expect(area.lng).toBeLessThan(128.0);
    }
  });

  test("이름이 비어 있지 않다", () => {
    for (const area of AREAS) expect(area.name.trim()).not.toBe("");
  });
});

/*
 * 위치를 못 얻었을 때 무엇을 고쳐야 하는지.
 *
 * 사용자가 Chrome의 "위치 액세스 허용됨" 알림과 우리 안내를 나란히 놓고
 * "허용했는데 왜 안 되냐"고 물었다. 둘 다 맞는 말이었다 — 사이트 권한은
 * 허용이고 OS가 막고 있었다. 한 문장으로 뭉뚱그리면 사용자는 이미 허용해 둔
 * 설정을 다시 확인하러 갔다가 그대로 돌아온다.
 */
describe("위치 차단 안내", () => {
  /*
   * 원인을 단정하지 않는다.
   *
   * 한동안 "사이트 권한이 허용인데 실패했으니 막는 쪽은 기기다"라고 적었다.
   * 그 추론은 막는 주체가 브라우저 아니면 기기 둘뿐이라고 전제한 것이었고,
   * 사용자가 기기 설정도 켜져 있는 화면을 보내면서 전제가 깨졌다. 그런데도
   * 화면은 계속 기기를 범인으로 지목하고 있었다.
   *
   * 화면이 볼 수 있는 건 "허용돼 있는데 좌표가 안 왔다"까지다. 거기서 멈춘다.
   */
  test("사이트 권한이 허용인데 실패하면 원인을 단정하지 않는다", () => {
    const message = geoBlockMessage("granted");
    expect(message).toMatch(/허용/);
    expect(message).not.toMatch(/기기가 막고|기기에서 위치를 받지/);
    // 이미 해 둔 일을 또 시키지 않는다.
    expect(message).not.toMatch(/사이트의 위치 접근을 허용/);
  });

  /*
   * 단정하지 않는다.
   *
   * 사용자가 macOS 위치 서비스에서 Chrome을 켠 스크린샷을 보내고도 여전히
   * 실패했다. 그 상태에서 "시스템 설정에서 켜야 해요"라고 지시하면, 앱이
   * 이미 해 둔 일을 계속 시키는 꼴이 된다. 우리는 기기 안에서 무슨 일이
   * 벌어지는지 볼 수 없다 — 못 받았다는 사실만 말하고 길을 준다.
   */
  test("기기 설정을 이래라저래라 지시하지 않는다", () => {
    const message = geoBlockMessage("granted");
    expect(message).not.toMatch(/켜야 해요|허용해 주세요|설정하세요/);
  });

  /* 모른다는 걸 숨기지 않는다. 숨기면 사용자가 엉뚱한 곳을 계속 고친다. */
  test("원인을 모를 때는 모른다고 말한다", () => {
    expect(geoBlockMessage("granted")).toMatch(/알 수 없|확인할 수 없/);
  });

  test("사이트 권한이 거부면 주소창을 가리킨다", () => {
    expect(geoBlockMessage("denied")).toMatch(/주소창/);
  });

  /* 아직 안 물어봤거나 알 수 없으면 한쪽으로 단정하지 않는다. */
  test("알 수 없으면 양쪽을 다 말한다", () => {
    for (const state of ["prompt", "unknown"] as const) {
      const message = geoBlockMessage(state);
      expect(message).toMatch(/브라우저/);
      expect(message).toMatch(/기기/);
    }
  });

  test("어느 경우든 빈 문장을 내놓지 않는다", () => {
    for (const state of ["granted", "denied", "prompt", "unknown"] as const) {
      expect(geoBlockMessage(state).trim().length).toBeGreaterThan(10);
    }
  });
});

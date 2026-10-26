import type { Charger, FavoriteStation, Station } from "@/lib/api/types";

/**
 * 충전소 화면 테스트가 공유하는 고정값과 스텁.
 *
 * 여기 있는 충전소는 **테스트 안에서만** 산다. 화면 코드에는 이런 상수가 한 개도
 * 없어야 한다 — 주변 충전소 API가 아직 501이라, 화면이 예시 데이터를 하나라도
 * 들고 있으면 시연에서 "이거 실제 데이터인가요" 한마디에 무너진다.
 * 그래서 목록이 그려지는 테스트는 전부 "서버가 계약대로 응답한 날"을 흉내 낸 것이고,
 * 501인 오늘의 화면에는 목록이 없다는 것을 따로 못 박아 둔다.
 */

/*
 * 실제 API 모양: 타입은 "02"·"04" 같은 코드, 속도는 capacity_kw가 말해 준다.
 * 상태도 원문 코드다 — "2"가 충전대기(사용 가능), "3"이 충전중.
 */
export const FAST_AVAILABLE: Charger = {
  charger_id: "c-fast",
  type: "04",
  capacity_kw: 100,
  status: "2",
  status_updated_at: "2026-09-21T22:10:00+09:00",
};

export const SLOW_CHARGING: Charger = {
  charger_id: "c-slow",
  type: "02",
  capacity_kw: 7,
  status: "3",
  status_updated_at: "2026-09-21T22:05:00+09:00",
};

/**
 * 공식 코드표(활용가이드 v1.25 3.2절)에 없는 상태 코드.
 * 실데이터에서 본 적은 없지만, 코드표가 개정되면 이런 값이 먼저 들어온다.
 */
export const UNKNOWN_STATUS: Charger = {
  charger_id: "c-unknown",
  type: "06",
  capacity_kw: 50,
  status: "7",
  status_updated_at: null,
};

/**
 * chargers에 null을 넣을 수 있게 열어 둔다. 계약상 Station의 chargers는 필수지만,
 * latestStatusUpdate 같은 계산은 null이 와도 화면을 세우지 않아야 한다.
 */
export function station(
  overrides: Partial<Omit<Station, "chargers">> & { chargers?: Charger[] | null } = {},
): Station {
  return {
    station_id: "ME000001",
    name: "서울역 공영주차장",
    address: "서울 중구 한강대로 405",
    lat: 37.5547,
    lng: 126.9707,
    distance_m: 320,
    operator: "한국전력",
    available_hours: "24시간",
    is_favorite: false,
    chargers: [FAST_AVAILABLE],
    ...overrides,
  } as Station;
}

/** 캐시 미적중이 기본값이다 — station_id 말고는 전부 null (API 명세서 7-4). */
export function favorite(overrides: Partial<FavoriteStation> = {}): FavoriteStation {
  return {
    station_id: "ME000001",
    name: null,
    address: null,
    lat: null,
    lng: null,
    distance_m: null,
    operator: null,
    available_hours: null,
    is_favorite: true,
    chargers: null,
    ...overrides,
  };
}

// ── navigator.geolocation 스텁 ──────────────────────────────────────────
//
// vi.stubGlobal("navigator", …)로 navigator를 통째로 갈아끼우지 않는다.
// userEvent가 navigator.clipboard 등을 쓰기 때문에 통째로 바꾸면 클릭 테스트가
// 엉뚱한 곳에서 터진다. 필요한 속성 하나만 configurable로 덮어쓴다.

export type GeoResult =
  | { kind: "granted"; lat: number; lng: number }
  /** 사용자가 권한을 거부함 (PERMISSION_DENIED) */
  | { kind: "denied" }
  /** 위치는 물어봤지만 못 받음 (POSITION_UNAVAILABLE) */
  | { kind: "failed" }
  /** 브라우저에 Geolocation API가 아예 없음 */
  | { kind: "missing" }
  /**
   * 성공도 실패도 돌려주지 않음.
   *
   * OS가 위치 서비스를 막았을 때 실제로 나타나는 실패 모드다. 에러가 오면
   * 그래도 화면이 반응하는데, 아무 응답이 없으면 timeout 옵션이 없는 한
   * 영원히 기다린다.
   */
  | { kind: "hang" };

/**
 * 결과를 배열로 주면 호출마다 하나씩 소비한다 — "다시 시도하면 이번엔 성공한다"를
 * 그대로 쓸 수 있게 하려는 것이다. 배열이 바닥나면 마지막 값을 계속 돌려준다.
 */
export function stubGeolocation(
  results: GeoResult | GeoResult[],
): { calls: number; options: (PositionOptions | undefined)[] } {
  const sequence = Array.isArray(results) ? results : [results];
  const counter = { calls: 0, options: [] as (PositionOptions | undefined)[] };

  const define = (value: unknown) => {
    Object.defineProperty(navigator, "geolocation", { value, configurable: true });
  };

  if (sequence.every((result) => result.kind === "missing")) {
    define(undefined);
    return counter;
  }

  define({
    getCurrentPosition(
      onSuccess: (position: { coords: { latitude: number; longitude: number } }) => void,
      onError: (error: { code: number; message: string }) => void,
      options?: PositionOptions,
    ) {
      const result = sequence[Math.min(counter.calls, sequence.length - 1)];
      counter.calls += 1;
      counter.options.push(options);
      // 아무것도 부르지 않는다. timeout 옵션이 없으면 화면이 여기 갇힌다.
      if (result.kind === "hang") return;
      if (result.kind === "granted") {
        onSuccess({ coords: { latitude: result.lat, longitude: result.lng } });
        return;
      }
      onError({ code: result.kind === "denied" ? 1 : 2, message: "" });
    },
  });
  return counter;
}

export function restoreGeolocation(): void {
  Reflect.deleteProperty(navigator, "geolocation");
}

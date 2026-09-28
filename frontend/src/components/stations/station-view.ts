import type { Charger, FavoriteStation, Station } from "@/lib/api/types";
import { parseKstWallClock } from "@/lib/format";

/**
 * 충전소 화면이 쓰는 순수 계산.
 *
 * 여기에 예시 충전소 같은 상수는 없다. 주변 충전소 API가 아직 501이라,
 * 화면 코드가 그럴듯한 데이터를 하나라도 들고 있으면 시연에서 무너진다.
 */

/**
 * 위치를 못 얻었을 때 고를 조회 기준점.
 *
 * 화면이 기기 좌표 하나에 걸려 있으면 안 된다. 사이트 권한이 "허용"이어도 OS가
 * 위치 서비스를 막으면 `getCurrentPosition`이 PERMISSION_DENIED로 떨어지고,
 * 사용자는 브라우저에서 아무리 허용을 눌러도 고칠 수 없다. 그때 빠져나갈 길이
 * 없으면 화면이 그냥 죽는다.
 *
 * **좌표는 짐작한 값이 아니라 실제 API로 결과를 확인한 것만 남겼다** (반경 2km):
 * 빛가람 158곳 · 광주 상무 328곳 · 목포 137곳 · 여수 127곳 · 순천 96곳.
 * 캐시가 전남·광주만 담고 있어 그 밖 좌표를 넣으면 조용히 빈 목록이 된다.
 */
export type Area = { id: string; name: string; lat: number; lng: number };

export const AREAS: Area[] = [
  // 기본값이 빛가람인 건 대회장이기도 하고, 데이터가 확실히 있는 곳이기도 하다.
  { id: "bitgaram", name: "빛가람혁신도시", lat: 35.0175, lng: 126.79 },
  { id: "gwangju", name: "광주 상무지구", lat: 35.152, lng: 126.851 },
  { id: "mokpo", name: "목포", lat: 34.8118, lng: 126.3922 },
  { id: "yeosu", name: "여수", lat: 34.7604, lng: 127.6622 },
  { id: "suncheon", name: "순천", lat: 34.9506, lng: 127.4872 },
];

export const DEFAULT_AREA = AREAS[0];

/**
 * 사이트 권한 상태. `navigator.permissions`가 없거나 물어보다 실패하면 unknown.
 */
export type GeoPermission = "granted" | "denied" | "prompt" | "unknown";

/**
 * 위치를 못 얻었을 때 **무엇을 고쳐야 하는지** 알려 준다.
 *
 * 한 문장으로 뭉뚱그리면 안 되는 이유가 실제로 드러났다. 사용자가 Chrome의
 * "위치 액세스 허용됨" 알림과 우리 안내를 나란히 놓고 "허용했는데 왜 안
 * 되냐"고 물었다. 둘 다 맞는 말이었다 — 사이트 권한은 허용이고 macOS가
 * 막고 있었다. "브라우저에서 허용해 주세요"라고 하면 이미 해 둔 일을 다시
 * 시키는 셈이고, 사용자는 확인만 하고 그대로 돌아온다.
 */
export function geoBlockMessage(permission: GeoPermission): string {
  switch (permission) {
    case "granted":
      /*
       * 사이트 권한이 허용인데 실패했다. 한동안 여기서 "그러니 막는 쪽은
       * 기기"라고 단정했는데, 그 추론은 **막는 주체가 브라우저 아니면 기기,
       * 둘뿐**이라는 전제 위에 있었다. 사용자가 기기 설정도 켜져 있는 화면을
       * 보내면서 그 전제가 깨졌고, 화면은 그제야 근거 없이 기기를 범인으로
       * 지목하고 있었다는 게 드러났다.
       *
       * 화면이 실제로 아는 건 "허용돼 있는데 좌표가 안 왔다"까지다. 거기서
       * 멈춘다. 모른다는 걸 숨기면 사용자가 엉뚱한 곳을 계속 고치게 된다.
       */
      return "위치 접근은 허용돼 있는데 좌표를 받지 못했어요. 원인은 화면에서 확인할 수 없어요.";
    case "denied":
      return "이 사이트의 위치 접근이 차단돼 있어요. 주소창 왼쪽 아이콘에서 허용할 수 있어요.";
    default:
      // 아직 안 물어봤거나 알 수 없다. 한쪽으로 단정하지 않는다.
      return "위치를 얻지 못했어요. 브라우저나 기기에서 위치 접근이 막혀 있을 수 있어요.";
  }
}

/** 이름이 아직 없는 즐겨찾기에 쓸 문구. 한 곳에만 둔다. */
export const NAME_MISSING = "이름을 아직 불러오지 못했어요";

export type StatusTone = "ok" | "warn" | "off";

export type StatusView = {
  label: string;
  tone: StatusTone;
  /** 뜻을 아는 코드인지. 모르면 필터가 '사용 가능'으로 세지 않는다. */
  known: boolean;
  available: boolean;
};

/*
 * 한국환경공단 활용가이드 v1.25(2026-07-01) 3.2절 stat 공통코드를 그대로 옮긴다.
 * 원본: docs/sources/한국환경공단_전기자동차 충전소 정보_OpenAPI활용가이드_v1.25.docx
 *
 * 서버는 원문 코드를 그대로 준다(API 명세서 2-4). 뜻은 여기서 한 번만 붙인다.
 * '사용 가능'은 2(충전대기) 하나뿐이다 — 하나라도 잘못 세면 사용자는 없는 자리를
 * 찾아 차를 몬다. 표에 없는 코드는 지어내지 않고 원문을 보여준다.
 */
const KNOWN_STATUS: Record<string, { label: string; tone: StatusTone; available: boolean }> = {
  "0": { label: "알 수 없음", tone: "off", available: false },
  "1": { label: "통신 이상", tone: "off", available: false },
  "2": { label: "사용 가능", tone: "ok", available: true },
  "3": { label: "충전 중", tone: "warn", available: false },
  "4": { label: "운영 중지", tone: "off", available: false },
  "5": { label: "점검 중", tone: "off", available: false },
  "6": { label: "예약 중", tone: "warn", available: false },
  "9": { label: "상태 미확인", tone: "off", available: false },
};

export function statusView(status: string): StatusView {
  const key = status.trim().toLowerCase();
  if (key === "") {
    return { label: "상태 없음", tone: "off", known: false, available: false };
  }
  const known = KNOWN_STATUS[key];
  if (known) {
    return { ...known, known: true };
  }
  // 원문을 그대로 보여준다. 지어낸 말보다 읽는 사람에게 정직하다.
  return { label: status.trim(), tone: "off", known: false, available: false };
}

/*
 * 활용가이드 v1.25(2026-07-01) 3.3절 chgerType 공통코드. 커넥터 모양이지 속도가
 * 아니다. 표에 없는 코드는 넘겨짚지 않는다 — 모양을 잘못 말하면 사용자는 꽂히지
 * 않는 충전기로 간다.
 */
const CONNECTOR: Record<string, string> = {
  "01": "DC차데모",
  "02": "AC완속",
  "03": "DC차데모+AC3상",
  "04": "DC콤보",
  "05": "DC차데모+DC콤보",
  "06": "DC차데모+AC3상+DC콤보",
  "07": "AC3상",
  "08": "DC콤보(완속)",
  "09": "NACS",
  "10": "DC콤보+NACS",
  "11": "DC콤보2(버스전용)",
};

export function connectorLabel(type: string): string | null {
  return CONNECTOR[type.trim()] ?? null;
}

/**
 * 급속/완속을 가르는 경계 (kW).
 *
 * 실데이터(전남광주 32,835대)에서 41~49 kW는 한 대도 없다 —
 * 40 kW가 2대, 50 kW가 1,052대로 그 사이가 비어 있다. 임의로 고른 값이 아니다.
 */
export const FAST_MIN_KW = 50;

export type ChargeSpeed = "fast" | "slow" | "unknown";

/**
 * 충전 속도는 **타입 코드가 아니라 출력으로** 정한다.
 *
 * 타입은 속도를 결정하지 못한다 — 실데이터에서 type=04가 7~350 kW에 걸쳐
 * 있고 그중 137대는 50 kW 미만이다. 타입으로 가르면 수백 대가 틀린다.
 * 타입 코드의 뜻은 커넥터 종류다(활용가이드 3.3절: 02 AC완속, 04 DC콤보 …) —
 * 꽂는 모양을 말할 뿐 속도를 말하지 않는다.
 *
 * capacity_kw는 API가 주는 실측값이라 넘겨짚을 여지가 없다.
 * 다만 0 kW인 충전기가 20대 실제로 있어, 그건 완속이라 말하지 않는다.
 */
export function speedOf(capacityKw: number): ChargeSpeed {
  if (!Number.isFinite(capacityKw) || capacityKw <= 0) return "unknown";
  return capacityKw >= FAST_MIN_KW ? "fast" : "slow";
}

const SPEED_LABEL: Record<ChargeSpeed, string> = {
  fast: "급속",
  slow: "완속",
  unknown: "출력 정보 없음",
};

export function speedLabel(capacityKw: number): string {
  return SPEED_LABEL[speedOf(capacityKw)];
}

/** "320 m" · "1.2 km". 모르면 빈 문자열 — 0 km라고 단정하지 않는다. */
export function formatDistance(meters: number | null): string {
  if (meters === null) return "";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

/** 소수점이 필요 없으면 붙이지 않는다. "100" · "3.5" */
export function formatCapacity(kw: number): string {
  return Number.isInteger(kw) ? String(kw) : String(kw);
}

/** null과 빈 칸을 빼고 가운뎃점으로 잇는다. */
export function metaLine(parts: (string | null | undefined)[]): string {
  return parts
    .map((part) => part?.trim() ?? "")
    .filter((part) => part !== "")
    .join(" · ");
}

export type StationFilter = {
  /** "fast"·"slow"는 출력(kW) 기준이다. 타입 코드가 아니다 — speedOf 참고. */
  type: "all" | "fast" | "slow";
  availableOnly: boolean;
};

/**
 * 속도와 상태 조건은 **같은 충전기 한 대가 동시에** 만족해야 한다.
 * 따로 세면 "급속은 충전 중이고 완속만 비어 있는 곳"이 '급속 + 사용 가능만'에 걸린다.
 */
export function filterStations<T extends { chargers: Charger[] | null }>(
  stations: T[],
  filter: StationFilter,
): T[] {
  if (filter.type === "all" && !filter.availableOnly) return stations;
  return stations.filter((item) =>
    (item.chargers ?? []).some((charger) => {
      const speedOk = filter.type === "all" || speedOf(charger.capacity_kw) === filter.type;
      const statusOk = !filter.availableOnly || statusView(charger.status).available;
      return speedOk && statusOk;
    }),
  );
}

/** 충전기들 중 가장 최근 갱신 시각. 하나도 없으면 null. */
export function latestStatusUpdate(
  stations: { chargers: Charger[] | null }[],
): string | null {
  let latest: string | null = null;
  for (const item of stations) {
    for (const charger of item.chargers ?? []) {
      const at = charger.status_updated_at;
      if (at === null) continue;
      if (latest === null || at > latest) latest = at;
    }
  }
  return latest;
}

/** "상태 갱신 22:10". 시각이 없거나 못 읽으면 지금 시각을 적지 않고 없다고 말한다. */
export function statusUpdatedLabel(iso: string | null): string {
  if (iso === null) return "상태 갱신 시각 없음";
  try {
    const { hour, minute } = parseKstWallClock(iso);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `상태 갱신 ${pad(hour)}:${pad(minute)}`;
  } catch {
    return "상태 갱신 시각 없음";
  }
}

/** 충전소 이름 자리에 쓸 것. 이름이 없으면 그 사실을 말한다. */
export function displayName(item: Station | FavoriteStation): {
  name: string;
  missing: boolean;
} {
  const name = item.name?.trim() ?? "";
  return name === "" ? { name: NAME_MISSING, missing: true } : { name, missing: false };
}

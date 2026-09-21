import type { Charger, FavoriteStation, Station } from "@/lib/api/types";
import { parseKstWallClock } from "@/lib/format";

/**
 * 충전소 화면이 쓰는 순수 계산.
 *
 * 여기에 예시 충전소 같은 상수는 없다. 주변 충전소 API가 아직 501이라,
 * 화면 코드가 그럴듯한 데이터를 하나라도 들고 있으면 시연에서 무너진다.
 */

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
 * 뜻이 코드에 적혀 있는 값만 옮긴다.
 *
 * 명세 2-4가 "상태 코드 매핑은 원본 API 문서 확인 후 확정"으로 남아 있고,
 * 한국환경공단 원본은 "1".."9" 같은 숫자를 쓴다. 모르는 코드를 '사용 가능'으로
 * 넘겨짚으면 사용자는 없는 자리를 찾아 차를 몬다.
 */
const KNOWN_STATUS: Record<string, { label: string; tone: StatusTone; available: boolean }> = {
  available: { label: "사용 가능", tone: "ok", available: true },
  charging: { label: "충전 중", tone: "warn", available: false },
  maintenance: { label: "점검 중", tone: "off", available: false },
  unavailable: { label: "사용 불가", tone: "off", available: false },
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

const KNOWN_TYPE: Record<string, string> = { fast: "급속", slow: "완속" };

/** 자기 뜻을 적어 보낸 값만 옮기고 나머지는 원문을 남긴다. */
export function chargerTypeLabel(type: string): string {
  return KNOWN_TYPE[type.trim().toLowerCase()] ?? type;
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
  type: "all" | "fast" | "slow";
  availableOnly: boolean;
};

/**
 * 종류와 상태 조건은 **같은 충전기 한 대가 동시에** 만족해야 한다.
 * 따로 세면 "급속은 충전 중이고 완속만 비어 있는 곳"이 '급속 + 사용 가능만'에 걸린다.
 */
export function filterStations<T extends { chargers: Charger[] | null }>(
  stations: T[],
  filter: StationFilter,
): T[] {
  if (filter.type === "all" && !filter.availableOnly) return stations;
  return stations.filter((item) =>
    (item.chargers ?? []).some((charger) => {
      const typeOk = filter.type === "all" || charger.type.trim().toLowerCase() === filter.type;
      const statusOk = !filter.availableOnly || statusView(charger.status).available;
      return typeOk && statusOk;
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

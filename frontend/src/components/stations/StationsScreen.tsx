"use client";

import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { PageContainer } from "@/components/shell/AppShell";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { addFavorite, fetchStations, removeFavorite } from "@/lib/api/endpoints";
import type { Station } from "@/lib/api/types";

import { todayInSeoul } from "@/components/timeline/timeline-view";

import { StationCard } from "./StationCard";
import { StationMap } from "./StationMap";
import {
  AREAS,
  DEFAULT_AREA,
  geoBlockMessage,
  type GeoPermission,
  FAST_MIN_KW,
  type Area,
  filterStations,
  latestStatusUpdate,
  statusUpdatedLabel,
  statusView,
  type StationFilter,
} from "./station-view";

/**
 * 주변 충전소.
 *
 * GET /api/chargers가 아직 501이다. 그래도 **호출은 실제로 해 본다** — 501을 미리
 * 넘겨짚고 안내만 띄우면, 백엔드가 들어온 날 이 화면이 도는지 아무도 모른다.
 * 501이 오면 이유를 밝히고 목록을 만들지 않는다. 껍데기 카드도 두지 않는다.
 */

type Coords = { lat: number; lng: number };

/**
 * 좌표를 어디서 얻었는지.
 *
 * 화면이 이걸 밝혀야 한다 — 기본 지역으로 찾아 놓고 "내 주변"이라고 하면
 * 사용자는 자기 근처에 이 충전소들이 있다고 믿는다.
 */
type Origin = { kind: "device" } | { kind: "area"; area: Area };

type GeoState =
  | { kind: "asking" }
  | { kind: "ready"; coords: Coords; origin: Origin };

/**
 * 위치 요청에 거는 제한 시간.
 *
 * 없으면 OS가 응답을 주지 않을 때 화면이 영원히 로딩에 갇힌다. 에러가 오는
 * 것보다 나쁜 실패 모드다 — 에러는 최소한 다음 화면을 그릴 수 있다.
 */
const GEO_TIMEOUT_MS = 8000;

const SIGN_IN_HREF = `/login?next=${encodeURIComponent("/stations")}`;

const TYPE_OPTIONS: { value: StationFilter["type"]; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "fast", label: "급속" },
  { value: "slow", label: "완속" },
];

/**
 * 기기 위치를 물어본다. 못 얻으면 null.
 *
 * 실패를 종류별로 나누지 않는 건 화면이 할 일이 같기 때문이다. 사이트 권한이
 * "허용"이어도 OS가 막으면 PERMISSION_DENIED가 오는데, 그때 "브라우저에서
 * 허용해 주세요"라고 안내하면 사용자는 이미 허용해 둔 설정을 다시 확인하러
 * 갔다가 돌아온다. 어느 쪽이든 지금 할 수 있는 건 지역을 고르는 것이다.
 */
function askDeviceLocation(): Promise<Coords | null> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve(null);
      return;
    }
    let settled = false;
    const done = (value: Coords | null) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    navigator.geolocation.getCurrentPosition(
      (position) =>
        done({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => done(null),
      { timeout: GEO_TIMEOUT_MS, maximumAge: 5 * 60 * 1000 },
    );
    // 브라우저가 timeout 옵션을 지키지 않는 경우가 있어 우리도 한 번 더 건다.
    setTimeout(() => done(null), GEO_TIMEOUT_MS + 500);
  });
}

/**
 * 사이트 권한 상태를 물어본다. 실패는 곧 unknown이다 — 이걸 못 읽는다고
 * 위치 찾기 자체가 실패하면 안 된다.
 */
async function askPermission(): Promise<GeoPermission> {
  try {
    if (typeof navigator === "undefined" || !navigator.permissions?.query) return "unknown";
    const status = await navigator.permissions.query({ name: "geolocation" as PermissionName });
    return status.state as GeoPermission;
  } catch {
    return "unknown";
  }
}

function areaState(area: Area): GeoState {
  return { kind: "ready", coords: { lat: area.lat, lng: area.lng }, origin: { kind: "area", area } };
}

export function StationsScreen() {
  const { status } = useSession();
  const [geo, setGeo] = useState<GeoState>({ kind: "asking" });
  /** "내 위치로 찾기"가 도는 중. geo를 asking으로 되돌리지 않아 지도가 안 깜빡인다. */
  const [locating, setLocating] = useState(false);
  const [geoNotice, setGeoNotice] = useState<string | null>(null);
  const [stations, setStations] = useState<Station[] | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [filter, setFilter] = useState<StationFilter>({ type: "all", availableOnly: false });
  const [favorites, setFavorites] = useState<Record<string, boolean>>({});
  const [favoriteError, setFavoriteError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  /**
   * 기기 위치를 (다시) 물어본다.
   *
   * 못 얻으면 **보던 지역을 그대로 두고 그 사실을 말한다.** 예전엔 조용히
   * 기본 지역으로 되돌렸는데, 기본 지역을 보던 사람에게는 결과가 같은
   * 화면이라 버튼이 고장난 것처럼 보였다 — 실제로 그렇게 보고됐다.
   * 목포를 보다가 눌렀는데 빛가람으로 끌려가는 것도 같은 이유로 안 된다.
   *
   * 로딩 중에 지도를 지우지 않는 것도 의도다. 화면이 깜빡였다 같은 자리로
   * 돌아오면 무슨 일이 일어난 건지 알 수 없다.
   */
  const useMyLocation = useCallback(() => {
    setLocating(true);
    setGeoNotice(null);
    void askDeviceLocation().then((coords) => {
      setLocating(false);
      if (coords === null) {
        /*
         * 왜 실패했는지까지 봐야 쓸모 있는 안내가 된다. 사이트 권한이 허용인데
         * 실패했다면 막는 쪽은 기기다 — 그때 "브라우저에서 허용해 주세요"라고
         * 하면 이미 해 둔 일을 다시 시키는 셈이다.
         */
        void askPermission().then((permission) => setGeoNotice(geoBlockMessage(permission)));
        return;
      }
      setGeo({ kind: "ready", coords, origin: { kind: "device" } });
    });
  }, []);

  const selectArea = useCallback((id: string) => {
    const found = AREAS.find((area) => area.id === id);
    if (!found) return;
    setGeoNotice(null);
    setGeo(areaState(found));
  }, []);

  /*
   * 마운트 때 한 번 물어보고, 못 얻으면 기본 지역으로 넘어간다.
   *
   * 답을 기다리는 동안(최대 8초) 사용자가 먼저 지역을 골랐다면 그 선택이
   * 이긴다. 뒤늦게 온 위치가 덮어쓰면 고른 지역이 말없이 다른 곳으로 바뀐다.
   */
  useEffect(() => {
    let alive = true;
    void askDeviceLocation().then((coords) => {
      if (!alive) return;
      setGeo((prev) =>
        prev.kind !== "asking"
          ? prev
          : coords === null
            ? areaState(DEFAULT_AREA)
            : { kind: "ready", coords, origin: { kind: "device" } },
      );
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (geo.kind !== "ready") return;
    let alive = true;
    fetchStations({ lat: geo.coords.lat, lng: geo.coords.lng })
      .then((found) => {
        if (!alive) return;
        setStations(found);
        setLoadError(null);
        setFavorites(
          Object.fromEntries(
            found.map((item) => [item.station_id, item.is_favorite === true]),
          ),
        );
      })
      .catch((caught: unknown) => {
        if (!alive) return;
        setStations(null);
        setLoadError(
          caught instanceof ApiError ? caught : new ApiError(0, "충전소를 불러오지 못했어요."),
        );
      });
    return () => {
      alive = false;
    };
  }, [geo]);

  const loggedIn = status === "authenticated";

  function toggleFavorite(id: string) {
    const next = !favorites[id];
    setBusyId(id);
    setFavoriteError(null);
    const request = next ? addFavorite(id) : removeFavorite(id);
    void request
      // 서버가 받아준 뒤에만 별을 바꾼다. 실패했는데 눌린 것처럼 굴면
      // 사용자는 담았다고 믿고 다음에 즐겨찾기에서 못 찾는다.
      .then(() => setFavorites((prev) => ({ ...prev, [id]: next })))
      .catch((caught: unknown) =>
        setFavoriteError(caught instanceof Error ? caught.message : "저장하지 못했어요."),
      )
      .finally(() => setBusyId(null));
  }

  const currentAreaId = geo.kind === "ready" && geo.origin.kind === "area" ? geo.origin.area.id : null;
  const visible = stations === null ? [] : filterStations(stations, filter);
  const hasUnknownStatus = visible.some((item) =>
    (item.chargers ?? []).some((charger) => !statusView(charger.status).known),
  );

  return (
    <PageContainer className="pb-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-title text-ink lg:text-title-lg">
          주변 충전소
        </h1>
        <ButtonLink href="/me/favorites" variant="ghost" className="text-sm">
          즐겨찾기
        </ButtonLink>
      </div>

      <div className="mt-5 flex flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start lg:gap-8">
        <div className="min-w-0">

          {/*
           * 어디를 기준으로 찾는지 늘 보이게 두고, 지역 고르개는 **늘** 둔다.
           *
           * 기기 위치를 못 얻어도 화면이 죽지 않아야 한다 — 사이트 권한이
           * "허용"인데 OS가 막으면 PERMISSION_DENIED가 오고, 사용자는
           * 브라우저에서 고칠 수 없다. 그때 기본 지역으로 넘어가되 "내 주변"인
           * 척하지 않는 것이 중요하다.
           *
           * 위치를 얻었을 때 고르개를 숨기던 시절이 있었는데, 캐시가 전남·광주만
           * 담고 있어서 다른 지역에서 위치를 허용한 사람은 빈 목록만 보고 갈 곳이
           * 없었다. 그래서 내 위치는 기본값일 뿐이고, 고르개의 맨 위 항목으로
           * "내 위치"를 보여 준다. 그 항목은 고를 수 없다 — 위치를 다시 묻는 건
           * 옆의 버튼이 한다. 고르개에서 고르게 하면 실패했을 때 고르개가
           * 엉뚱한 값을 가리킨다.
           */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <span className="font-bold text-ink">지역</span>
              <select
                aria-label="지역"
                value={currentAreaId ?? ""}
                onChange={(event) => selectArea(event.target.value)}
                className={`min-h-12 rounded-field border border-line bg-field px-3 py-2 text-sm focus-visible:border-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand
                  ${currentAreaId === null && geo.kind === "ready" ? "font-bold text-brand" : "text-ink"}`}
              >
                {currentAreaId === null ? (
                  <option value="" disabled>
                    {geo.kind === "asking" ? "위치 확인 중…" : "내 위치 기준"}
                  </option>
                ) : null}
                {AREAS.map((area) => (
                  <option key={area.id} value={area.id}>
                    {area.name}
                  </option>
                ))}
              </select>
            </label>

            <Button
              type="button"
              onClick={useMyLocation}
              disabled={locating}
              variant="ghost"
              className="text-sm"
            >
              {locating ? "위치 확인 중…" : "내 위치로 찾기"}
            </Button>
          </div>

          {/*
           * 눌렀는데 아무 일도 안 일어나는 것처럼 보이면 안 된다. 기본 지역을
           * 보던 사람에게는 실패 결과가 같은 화면이라, 말해 주지 않으면 버튼이
           * 고장난 줄 안다.
           */}
          {geoNotice ? (
            <p role="status" className="mt-2 rounded-field bg-warn-bg px-3.5 py-2.5 text-sm text-warn-fg">
              {geoNotice} 지역을 골라 찾아볼 수 있어요.
            </p>
          ) : null}

          <fieldset className="mt-4">
            <legend className="sr-only">충전기 종류</legend>
            <div className="flex flex-wrap items-center gap-2">
              {TYPE_OPTIONS.map((option) => {
                const selected = filter.type === option.value;
                return (
                  <label
                    key={option.value}
                    className={`inline-flex min-h-11 cursor-pointer items-center rounded-pill px-4 text-sm font-bold transition-colors duration-150
                      has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand
                      ${selected ? "bg-ink text-white" : "border border-line bg-surface text-ink-2"}`}
                  >
                    <input
                      type="radio"
                      name="charger-type"
                      className="sr-only"
                      checked={selected}
                      onChange={() => setFilter((prev) => ({ ...prev, type: option.value }))}
                    />
                    {option.label}
                  </label>
                );
              })}

              <label className="ml-auto flex min-h-11 cursor-pointer items-center gap-2 text-sm text-ink-2">
                <input
                  type="checkbox"
                  checked={filter.availableOnly}
                  onChange={(event) =>
                    setFilter((prev) => ({ ...prev, availableOnly: event.target.checked }))
                  }
                  className="size-4 accent-brand"
                />
                사용 가능만
              </label>
            </div>
          </fieldset>

          {/*
            * 급속/완속 기준을 화면에 적는다. 타입 코드로 가르지 않고 출력으로 가르는데,
            * 그 경계를 숨기면 "왜 이게 급속이지"에 답할 수 없다.
            */}
          {filter.type !== "all" ? (
            <p className="mt-2 text-sm text-ink-2">
              충전기 출력 기준으로 나눠요 — 급속 {FAST_MIN_KW} kW 이상, 완속 그 미만.
            </p>
          ) : null}

          {filter.availableOnly ? (
            <p className="mt-2 text-sm text-ink-2">
              지금 충전대기인 충전기가 있는 곳만 남겨요. 공식 코드표에 없는 상태 코드는 세지 않아요.
            </p>
          ) : null}

          {favoriteError ? (
            <div role="alert" className="mt-4 rounded-field bg-warn-bg px-4 py-3 text-sm text-warn-fg">
              {favoriteError}
            </div>
          ) : null}

          <div className="mt-4">
            {geo.kind === "asking" ? (
              <div className="h-24 animate-pulse rounded-card bg-sunken" aria-hidden />
            ) : loadError ? (
              <Notice>
                {loadError.notImplemented ? (
                  <>
                    <strong className="block font-bold">주변 충전소는 아직 준비 중이에요.</strong>
                    <span className="mt-1 block">
                      한국환경공단 전기자동차 충전소 정보 API 연동이 끝나면 열려요.
                    </span>
                  </>
                ) : (
                  loadError.message
                )}
              </Notice>
            ) : stations === null ? (
              <div className="h-24 animate-pulse rounded-card bg-sunken" aria-hidden />
            ) : stations.length === 0 ? (
              /*
               * "충전소가 없다"와 "이 지역은 아직 수집하지 않았다"는 다른 말이다.
               * 지금 캐시는 전남·광주만 담고 있어서, 서울에서 열면 빈 목록이
               * 온다 — 그걸 "주변에 없다"고 하면 거짓말이 된다. 어느 쪽인지
               * 프론트가 알 수 없으므로 둘 다 말하고 지역을 고를 길을 준다.
               *
               * "지역을 바꿔 보세요"라고만 하면 어디서 바꾸는지 찾아야 한다. 말한
               * 자리에서 바로 누를 수 있게 수집된 지역을 늘어놓는다. 지금 보는
               * 지역은 빼야 한다 — 눌러도 같은 빈 화면이면 고장으로 읽힌다.
               */
              <div className="rounded-card border border-line bg-surface px-5 py-8 text-center">
                <p className="text-ink-2">이 근처에서 충전소를 찾지 못했어요</p>
                <p className="mt-2 text-sm text-ink-2">
                  지금은 전남·광주 지역 충전소만 수집돼 있어요. 아래 지역에서 찾아보세요.
                </p>
                <div
                  role="group"
                  aria-label="수집된 지역"
                  className="mt-4 flex flex-wrap justify-center gap-2"
                >
                  {AREAS.filter((area) => area.id !== currentAreaId).map((area) => (
                    <button
                      key={area.id}
                      type="button"
                      onClick={() => selectArea(area.id)}
                      className="inline-flex min-h-11 items-center rounded-pill border border-line bg-surface px-4 text-sm font-bold text-ink-2 transition-colors duration-150
                        hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                    >
                      {area.name}
                    </button>
                  ))}
                </div>
              </div>
            ) : visible.length === 0 ? (
              <p className="rounded-card border border-line bg-surface px-5 py-8 text-center text-ink-2">
                고른 조건에 맞는 충전소가 없어요
              </p>
            ) : (
              <ul aria-label="충전소 목록" className="flex flex-col gap-3">
                {visible.map((item) => (
                  <StationCard
                    key={item.station_id}
                    station={item}
                    favorite={
                      loggedIn
                        ? {
                            pressed: favorites[item.station_id] === true,
                            busy: busyId === item.station_id,
                            onToggle: () => toggleFavorite(item.station_id),
                          }
                        : undefined
                    }
                    signInHref={loggedIn ? undefined : SIGN_IN_HREF}
                  />
                ))}
              </ul>
            )}
          </div>

          {hasUnknownStatus ? (
            <p className="mt-3 text-sm leading-relaxed text-ink-2">
              공식 코드표에 없는 상태 코드는 원문 그대로 보여드려요. 뜻을 넘겨짚으면
              없는 자리를 찾아가게 돼요.
            </p>
          ) : null}

          <p className="mt-4 text-sm leading-relaxed text-ink-2">
            {statusUpdatedLabel(latestStatusUpdate(stations ?? []), todayInSeoul())} · 출처: 한국환경공단
            전기자동차 충전소 정보 · 위치는 조회에만 쓰고 저장하지 않아요
          </p>
        </div>

        {/*
         * 지도는 **하나만** 만든다.
         *
         * 모바일용·데스크톱용을 따로 두면 둘 다 마운트되고 하나는 늘
         * display:none이다. Leaflet은 크기 0인 상자에서 초기화되면 타일 위치를
         * 잘못 잡고, 화면이 넓어져도 스스로 고치지 못한다. 높이만 반응형으로
         * 바꾸고 순서로 자리를 옮긴다 — 모바일에서는 목록 위, 데스크톱에서는
         * 오른쪽 칸(시안 p-18).
         */}
        {geo.kind === "ready" ? (
          <StationMap
            center={geo.coords}
            stations={stations}
            className="order-first mt-4 h-44 lg:order-none lg:mt-0 lg:h-[520px]"
          />
        ) : (
          <div
            className="order-first mt-4 h-44 animate-pulse rounded-card bg-sunken lg:order-none lg:mt-0 lg:h-[520px]"
            aria-hidden
          />
        )}
      </div>
    </PageContainer>
  );
}

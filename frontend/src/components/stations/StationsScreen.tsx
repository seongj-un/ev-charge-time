"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
  geoFailureMessage,
  type GeoFailure,
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
type Origin = { kind: "device" } | { kind: "pin" } | { kind: "area"; area: Area };

type GeoState =
  | { kind: "asking" }
  | { kind: "ready"; coords: Coords; origin: Origin };

/**
 * 위치 요청에 거는 제한 시간(getCurrentPosition의 timeout 옵션).
 *
 * 없으면 OS가 응답을 주지 않을 때 화면이 영원히 로딩에 갇힌다. 그렇다고 짧게
 * 잡으면 안 된다 — 8초였을 때 macOS Chrome에서 "허용돼 있는데 좌표를 받지
 * 못했어요"가 났다. 노트북은 GPS가 없어 Wi-Fi로 위치를 잡는데 첫 측위가 8초를
 * 넘는 일이 흔하고, 그러면 TIMEOUT으로 떨어진다. 권한도 설정도 다 켜져 있는데
 * 실패하던 이유다.
 */
const GEO_TIMEOUT_MS = 30_000;

/**
 * 우리 쪽 안전망. 브라우저가 timeout 옵션을 안 지킬 때를 위한 것이다.
 * timeout 옵션은 권한 창에 답한 **뒤부터** 세므로, 권한 창이 떠 있는 시간까지
 * 넉넉히 더한다 — 8.5초짜리 안전망은 "허용"을 천천히 누른 사람의 위치를 버렸다.
 */
const GEO_BACKSTOP_MS = GEO_TIMEOUT_MS + 30_000;

/**
 * 처음 열 때 이만큼 기다려도 위치가 안 오면 기본 지역을 먼저 보여 준다. 위치
 * 요청은 계속 기다리고, 늦게라도 오면(그사이 지역을 고르지 않았다면) 내 위치로 바꾼다.
 */
const MOUNT_FALLBACK_MS = 8000;

const SIGN_IN_HREF = `/login?next=${encodeURIComponent("/stations")}`;

const TYPE_OPTIONS: { value: StationFilter["type"]; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "fast", label: "급속" },
  { value: "slow", label: "완속" },
];

/**
 * 위치 실패를 서버 로그에 남긴다(좌표는 없다 — 실패했으니 애초에 없다).
 *
 * 원인을 사용자 화면 캡처로만 추측하다 보니 "설정을 확인해 보세요"를 되풀이했다.
 * 실패 종류·사이트 권한·브라우저를 남겨 두면 원인을 서버에서 직접 본다.
 * 보내기가 실패해도 화면에는 영향이 없다.
 */
function reportGeoFailure(failure: GeoFailure, permission: GeoPermission) {
  try {
    const body = JSON.stringify({ failure, permission });
    if (typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon("/geo-report", new Blob([body], { type: "application/json" }));
    }
  } catch {
    // 진단용이다. 실패해도 조용히 넘긴다.
  }
}

type GeoResult = { ok: true; coords: Coords } | { ok: false; failure: GeoFailure };

/**
 * 기기 위치를 물어본다.
 *
 * 실패는 종류를 남긴다(거부·못 찾음·시간 초과). 예전엔 전부 null로 뭉쳐서
 * 화면이 "좌표를 받지 못했어요"까지밖에 말할 수 없었고, 실제 원인(시간 초과)을
 * 아무도 못 봤다.
 */
function askDeviceLocation(): Promise<GeoResult> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve({ ok: false, failure: "unsupported" });
      return;
    }
    let settled = false;
    const done = (value: GeoResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(backstop);
      resolve(value);
    };
    // 브라우저가 timeout 옵션을 지키지 않는 경우가 있어 우리도 한 번 더 건다.
    const backstop = setTimeout(() => done({ ok: false, failure: "timeout" }), GEO_BACKSTOP_MS);
    navigator.geolocation.getCurrentPosition(
      (position) =>
        done({ ok: true, coords: { lat: position.coords.latitude, lng: position.coords.longitude } }),
      (error) =>
        done({
          ok: false,
          failure: error?.code === 1 ? "denied" : error?.code === 3 ? "timeout" : "unavailable",
        }),
      { timeout: GEO_TIMEOUT_MS, maximumAge: 5 * 60 * 1000 },
    );
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
   * 지금 유효한 위치 요청의 번호. 지역을 고르거나 새로 물어보면 올라간다 —
   * 그보다 앞선 요청의 답이 늦게 와도 버린다. 고른 지역이 말없이 바뀌면 안 된다.
   */
  const requestRef = useRef(0);

  /** 실패 안내. 사이트 권한 상태까지 봐야 쓸모 있는 말이 된다. */
  const explainFailure = useCallback((failure: GeoFailure, id: number) => {
    void askPermission().then((permission) => {
      reportGeoFailure(failure, permission);
      if (requestRef.current !== id) return;
      setGeoNotice(geoFailureMessage(failure, permission, GEO_TIMEOUT_MS / 1000));
    });
  }, []);

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
    const id = ++requestRef.current;
    setLocating(true);
    setGeoNotice(null);
    void askDeviceLocation().then((result) => {
      if (requestRef.current !== id) return;
      setLocating(false);
      if (!result.ok) {
        explainFailure(result.failure, id);
        return;
      }
      setGeo({ kind: "ready", coords: result.coords, origin: { kind: "device" } });
    });
  }, [explainFailure]);

  /**
   * 지도를 눌러 기준점을 정한다.
   *
   * 브라우저 위치는 브라우저와 OS가 둘 다 내줘야 온다. 그중 하나라도 막히면 화면이
   * 할 수 있는 게 없었고, 안내 문구로 사용자에게 설정을 고치게 할 수밖에 없었다.
   * 지도를 누르는 건 어느 브라우저에서나 된다 — 위치 기능과 무관한 길을 하나 둔다.
   */
  const pickOnMap = useCallback((coords: Coords) => {
    requestRef.current += 1;
    setLocating(false);
    setGeoNotice(null);
    setGeo({ kind: "ready", coords, origin: { kind: "pin" } });
  }, []);

  const selectArea = useCallback((id: string) => {
    const found = AREAS.find((area) => area.id === id);
    if (!found) return;
    // 기다리던 위치 요청은 버린다. 늦게 와서 고른 지역을 덮으면 안 된다.
    requestRef.current += 1;
    setLocating(false);
    setGeoNotice(null);
    setGeo(areaState(found));
  }, []);

  /*
   * 마운트 때 한 번 물어본다.
   *
   * 8초 안에 답이 없으면 기본 지역을 먼저 보여 주되 요청은 계속 기다린다.
   * 늦게라도 위치가 오면 내 위치로 바꾼다 — 예전엔 8.5초에서 요청을 버려서,
   * 첫 측위가 느린 노트북이나 권한 창을 천천히 누른 사람은 늘 빛가람에 남았다.
   * 그사이 사용자가 지역을 골랐다면 그 선택이 이긴다(requestRef).
   */
  useEffect(() => {
    let alive = true;
    const id = ++requestRef.current;
    const fallback = setTimeout(() => {
      if (!alive || requestRef.current !== id) return;
      setGeo((prev) => (prev.kind === "asking" ? areaState(DEFAULT_AREA) : prev));
      setGeoNotice(`내 위치를 확인하는 중이에요. 그동안 ${DEFAULT_AREA.name} 기준으로 보여 드려요.`);
    }, MOUNT_FALLBACK_MS);
    void askDeviceLocation().then((result) => {
      clearTimeout(fallback);
      if (!alive || requestRef.current !== id) return;
      if (result.ok) {
        setGeoNotice(null);
        setGeo({ kind: "ready", coords: result.coords, origin: { kind: "device" } });
        return;
      }
      setGeo((prev) => (prev.kind === "asking" ? areaState(DEFAULT_AREA) : prev));
      // 위치 기능이 없거나 권한 창에서 거부한 건 사용자가 이미 아는 일이다. 말없이 기본 지역을 보인다.
      if (result.failure === "timeout" || result.failure === "unavailable") {
        explainFailure(result.failure, id);
      } else {
        setGeoNotice(null);
      }
    });
    return () => {
      alive = false;
      clearTimeout(fallback);
    };
  }, [explainFailure]);

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
                    {geo.kind === "asking"
                      ? "위치 확인 중…"
                      : geo.origin.kind === "pin"
                        ? "지도에서 고른 곳"
                        : "내 위치 기준"}
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
              {geoNotice} 지도를 눌러 그 자리를 기준으로 찾거나, 지역을 골라 찾아볼 수 있어요.
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
          <div className="order-first mt-4 lg:order-none lg:mt-0">
            <StationMap
              center={geo.coords}
              stations={stations}
              onPick={pickOnMap}
              className="h-44 lg:h-[520px]"
            />
            <p className="mt-2 text-sm text-ink-2">지도를 누르면 그 자리를 기준으로 찾아요.</p>
          </div>
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

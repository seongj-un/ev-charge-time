"use client";

import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { PageContainer } from "@/components/shell/AppShell";
import { PinIcon } from "@/components/shell/icons";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { addFavorite, fetchStations, removeFavorite } from "@/lib/api/endpoints";
import type { Station } from "@/lib/api/types";

import { StationCard } from "./StationCard";
import {
  FAST_MIN_KW,
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

type GeoState =
  | { kind: "asking" }
  | { kind: "ready"; coords: Coords }
  /** 권한 거부 또는 위치 획득 실패 */
  | { kind: "denied" }
  /** 브라우저에 Geolocation API가 없음 */
  | { kind: "missing" };

const SIGN_IN_HREF = `/login?next=${encodeURIComponent("/stations")}`;

const TYPE_OPTIONS: { value: StationFilter["type"]; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "fast", label: "급속" },
  { value: "slow", label: "완속" },
];

function askLocation(): Promise<GeoState> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve({ kind: "missing" });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          kind: "ready",
          coords: { lat: position.coords.latitude, lng: position.coords.longitude },
        }),
      () => resolve({ kind: "denied" }),
    );
  });
}

export function StationsScreen() {
  const { status } = useSession();
  const [geo, setGeo] = useState<GeoState>({ kind: "asking" });
  const [stations, setStations] = useState<Station[] | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [filter, setFilter] = useState<StationFilter>({ type: "all", availableOnly: false });
  const [favorites, setFavorites] = useState<Record<string, boolean>>({});
  const [favoriteError, setFavoriteError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  /** 버튼에서 부른다. 이펙트 본문에서 부르면 동기 setState가 되어 lint에 걸린다. */
  const requestLocation = useCallback(() => {
    setGeo({ kind: "asking" });
    void askLocation().then(setGeo);
  }, []);

  // 처음 상태가 이미 asking이라, 마운트 때는 물어보기만 하면 된다.
  useEffect(() => {
    let alive = true;
    void askLocation().then((next) => {
      if (alive) setGeo(next);
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

  const visible = stations === null ? [] : filterStations(stations, filter);
  const hasUnknownStatus = visible.some((item) =>
    (item.chargers ?? []).some((charger) => !statusView(charger.status).known),
  );

  return (
    <PageContainer className="pb-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-ink lg:text-[28px]">
          주변 충전소
        </h1>
        <ButtonLink href="/me/favorites" variant="ghost" className="text-sm">
          즐겨찾기
        </ButtonLink>
      </div>

      <div className="mt-5 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start lg:gap-8">
        <div className="min-w-0">
          {/* 지도 자리. 시안도 자리표시자이고, 지도 없이도 목록으로 쓸 수 있다. */}
          <div
            className="flex h-44 flex-col items-center justify-center gap-2 rounded-card border border-dashed border-line bg-sunken text-ink-3 lg:hidden"
            aria-hidden
          >
            <PinIcon className="size-6" />
            <span className="text-sm">지도 영역</span>
          </div>

          <fieldset className="mt-4">
            <legend className="sr-only">충전기 종류</legend>
            <div className="flex flex-wrap items-center gap-2">
              {TYPE_OPTIONS.map((option) => {
                const selected = filter.type === option.value;
                return (
                  <label
                    key={option.value}
                    className={`cursor-pointer rounded-pill px-4 py-2 text-sm font-bold transition-colors
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

              <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm text-ink-2">
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
            <p className="mt-2 text-xs text-ink-3">
              충전기 출력 기준으로 나눠요 — 급속 {FAST_MIN_KW} kW 이상, 완속 그 미만.
            </p>
          ) : null}

          {filter.availableOnly ? (
            <p className="mt-2 text-xs text-ink-3">
              뜻이 확인된 코드만 남겨요. 아직 확정되지 않은 상태 코드는 빠집니다.
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
            ) : geo.kind !== "ready" ? (
              <section className="rounded-card border border-line bg-surface px-5 py-8 text-center">
                <p className="text-base font-bold text-ink">
                  위치를 알 수 없어 주변 충전소를 찾지 못했어요
                </p>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">
                  {geo.kind === "missing"
                    ? "이 브라우저는 위치 기능을 지원하지 않아요."
                    : "브라우저에서 위치 권한을 허용하면 가까운 충전소를 찾아드려요."}
                </p>
                <div className="mt-5">
                  <Button type="button" onClick={requestLocation} variant="outline" size="lg">
                    다시 시도
                  </Button>
                </div>
              </section>
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
              <p className="rounded-card border border-line bg-surface px-5 py-8 text-center text-ink-2">
                주변에 충전소가 없어요
              </p>
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
            <p className="mt-3 text-xs leading-relaxed text-ink-3">
              아직 확정되지 않은 상태 코드는 원문 그대로 보여드려요. 뜻을 넘겨짚으면
              없는 자리를 찾아가게 돼요.
            </p>
          ) : null}

          <p className="mt-4 text-xs leading-relaxed text-ink-3">
            {statusUpdatedLabel(latestStatusUpdate(stations ?? []))} · 출처: 한국환경공단
            전기자동차 충전소 정보 · 위치는 조회에만 쓰고 저장하지 않아요
          </p>
        </div>

        {/* 데스크톱에서는 지도가 오른쪽 큰 자리를 차지한다 (시안 p-18). */}
        <div
          className="hidden h-[520px] flex-col items-center justify-center gap-2 rounded-card border border-dashed border-line bg-sunken text-ink-3 lg:flex"
          aria-hidden
        >
          <PinIcon className="size-7" />
          <span className="text-sm">지도 영역</span>
        </div>
      </div>
    </PageContainer>
  );
}

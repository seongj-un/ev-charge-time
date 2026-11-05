"use client";

import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { MeLayout } from "@/components/me/MeSidebar";
import {
  LoadFailure,
  MeSkeleton,
  ServerUnreachable,
  SignInRequired,
} from "@/components/me/MeStates";
import { ButtonLink } from "@/components/ui/Button";
import { ApiError } from "@/lib/api/client";
import { fetchFavorites, removeFavorite } from "@/lib/api/endpoints";
import type { FavoriteStation } from "@/lib/api/types";

import { todayInSeoul } from "@/components/timeline/timeline-view";

import { StationCard } from "./StationCard";
import { latestStatusUpdate, statusUpdatedLabel } from "./station-view";

/**
 * 즐겨찾는 충전소.
 *
 * **이름이 없는 목록이 오늘의 정상 상태다.** 이름·주소·충전기는 GET /api/chargers가
 * 채우는 공유 캐시에서 오는데 그게 아직 501이라 캐시가 비어 있다 (API 명세서 7-4).
 * 시안(p-12·p-24)은 이름이 다 있는 그림이지만, 그걸 그릴 데이터가 없다.
 * 빈자리를 station_id로 메우지 않고 왜 없는지를 말한다.
 */
export function FavoritesScreen() {
  const { status, clear } = useSession();
  const [stations, setStations] = useState<FavoriteStation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStations(await fetchFavorites());
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.needsLogin) {
        // 요청 도중 세션이 끊긴 경우. 셸의 로그인 표시까지 같이 맞춰야 한다.
        clear();
        return;
      }
      setError(caught instanceof Error ? caught.message : "목록을 불러오지 못했어요.");
    }
  }, [clear]);

  useEffect(() => {
    if (status !== "authenticated") return;
    // 인라인으로 감싼다 — async 함수를 그대로 부르면 동기 setState로 읽혀 lint에 걸린다.
    void (async () => {
      await load();
    })();
  }, [status, load]);

  if (status === "loading") return <MeSkeleton />;
  if (status === "unreachable") return <ServerUnreachable title="즐겨찾는 충전소" />;
  if (status === "anonymous") {
    return (
      <SignInRequired
        next="/me/favorites"
        description="즐겨찾는 충전소는 계정에 저장돼요."
      />
    );
  }

  const updatedAt = statusUpdatedLabel(latestStatusUpdate(stations ?? []), todayInSeoul());
  // 충전소 정보(이름·주소)를 아직 못 받은 즐겨찾기가 있을 때만 그 사정을 말한다.
  const someUnnamed = (stations ?? []).some((item) => item.name === null || item.address === null);

  return (
    <MeLayout>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-title text-ink lg:text-title-lg">
          즐겨찾는 충전소
        </h1>
        <ButtonLink href="/stations" variant="ghost" className="text-sm">
          충전소 더 찾기
        </ButtonLink>
      </div>

      {error ? <div className="mt-5"><LoadFailure message={error} onRetry={() => void load()} /></div> : null}

      {stations === null ? (
        <div className="mt-5 h-24 animate-pulse rounded-card bg-sunken" aria-hidden />
      ) : stations.length === 0 ? (
        <section className="mt-5 rounded-card border border-line bg-surface px-5 py-10 text-center">
          <p className="text-base font-bold text-ink">아직 즐겨찾는 충전소가 없어요</p>
          {/* 보내놓고 막히면 더 나쁘다. 그쪽 사정을 미리 말한다. */}
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            주변 충전소에서 별을 눌러 담을 수 있어요. 다만 충전소 찾기는 한국환경공단
            API 연동 전이라 <strong className="font-bold">아직 열리지 않았어요.</strong>
          </p>
          <div className="mt-5">
            <ButtonLink href="/stations" variant="outline" size="lg">
              충전소 더 찾기
            </ButtonLink>
          </div>
        </section>
      ) : (
        <>
          <ul aria-label="즐겨찾는 충전소 목록" className="mt-5 flex flex-col gap-3">
            {stations.map((item) => (
              <StationCard
                key={item.station_id}
                station={item}
                favorite={{
                  pressed: true,
                  busy: busyId === item.station_id,
                  onToggle: () => {
                    setBusyId(item.station_id);
                    void removeFavorite(item.station_id)
                      .then(() => load())
                      .catch((caught: unknown) => {
                        // 실패했는데 목록에서 지우면 서버와 화면이 갈라진다.
                        setError(
                          caught instanceof Error ? caught.message : "해제하지 못했어요.",
                        );
                      })
                      .finally(() => setBusyId(null));
                  },
                }}
              />
            ))}
          </ul>

          <p className="mt-4 text-sm leading-relaxed text-ink-2">
            {updatedAt} · 출처: 한국환경공단 전기자동차 충전소 정보.
            {someUnnamed ? " 이름·주소가 비어 있는 곳은 충전소 정보가 다시 들어오면 채워져요." : null}
          </p>
        </>
      )}
    </MeLayout>
  );
}

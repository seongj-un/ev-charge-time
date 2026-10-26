"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/Badge";
import type { Charger, FavoriteStation, Station } from "@/lib/api/types";

import {
  connectorLabel,
  displayName,
  formatCapacity,
  formatDistance,
  metaLine,
  speedLabel,
  speedOf,
  statusView,
} from "./station-view";

/** 채워진 별 / 빈 별. 눌린 상태는 색이 아니라 aria-pressed가 나른다. */
function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
      <path
        d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8z"
        fill={filled ? "#E5A50A" : "none"}
        stroke={filled ? "#E5A50A" : "currentColor"}
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/*
 * 타입 코드(`02`·`04` …)는 코드가 아니라 커넥터 이름으로 보여준다(활용가이드
 * 3.3절). 속도는 타입이 정하지 못한다 — 같은 04(DC콤보)가 7 kW부터 350 kW까지
 * 있다. 그래서 급속·완속은 API가 실측값으로 주는 kW로 가른다.
 */
function ChargerRow({ charger }: { charger: Charger }) {
  const status = statusView(charger.status);
  const speed = speedOf(charger.capacity_kw);
  const connector = connectorLabel(charger.type);
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
      <span>{speedLabel(charger.capacity_kw)}</span>
      {speed === "unknown" ? null : (
        <>
          <span aria-hidden>·</span>
          <span className="tnum">{formatCapacity(charger.capacity_kw)} kW</span>
        </>
      )}
      {connector === null ? null : (
        <>
          <span aria-hidden>·</span>
          <span>{connector}</span>
        </>
      )}
      <Badge tone={status.tone}>{status.label}</Badge>
    </div>
  );
}

/**
 * 충전기 목록.
 *
 * null과 []를 다르게 말한다 (API 명세서 7-4). []는 "충전기가 0대인 충전소"고
 * null은 "아직 못 불러왔다"다. 같은 문장으로 그리면 사용자가 없는 충전소로 차를 몬다.
 */
function ChargerList({ chargers }: { chargers: Charger[] | null }) {
  if (chargers === null) {
    return <p className="text-sm text-ink-3">충전기 정보를 아직 불러오지 못했어요</p>;
  }
  if (chargers.length === 0) {
    return <p className="text-sm text-ink-3">등록된 충전기가 없어요</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {chargers.map((charger) => (
        <ChargerRow key={charger.charger_id} charger={charger} />
      ))}
    </div>
  );
}

type Props = {
  station: Station | FavoriteStation;
  /** 즐겨찾기 토글. 손님이면 주지 않고 signInHref를 준다. */
  favorite?: { pressed: boolean; onToggle: () => void; busy: boolean };
  signInHref?: string;
  children?: ReactNode;
};

export function StationCard({ station, favorite, signInHref, children }: Props) {
  const { name, missing } = displayName(station);
  const distance = formatDistance(station.distance_m);
  const meta = metaLine([station.address, station.operator, station.available_hours]);

  return (
    <li className="rounded-card border border-line bg-surface p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            {missing ? (
              // 이름 자리에 station_id를 키워 넣지 않는다. 없는 이름을 지어내는 것과 같다.
              <p className="text-sm font-bold text-ink-3">{name}</p>
            ) : (
              <h3 className="text-base font-bold text-ink">{name}</h3>
            )}
            {distance ? <span className="tnum text-sm text-ink-3">{distance}</span> : null}
          </div>

          <p className="mt-0.5 text-xs text-ink-3">
            <span className="tnum">{station.station_id}</span>
          </p>

          {meta ? <p className="mt-1.5 text-sm text-ink-2">{meta}</p> : null}

          <div className="mt-2.5">
            <ChargerList chargers={station.chargers} />
          </div>

          {children}
        </div>

        {favorite ? (
          <button
            type="button"
            aria-pressed={favorite.pressed}
            aria-label={`${missing ? `충전소 ${station.station_id}` : name} 즐겨찾기`}
            disabled={favorite.busy}
            onClick={favorite.onToggle}
            className="shrink-0 rounded-full p-2 text-ink-3 transition-colors hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
          >
            <StarIcon filled={favorite.pressed} />
          </button>
        ) : signInHref ? (
          // 손님에게 눌러도 안 되는 별을 주면 두 번 누르고 포기한다.
          <Link
            href={signInHref}
            aria-label={`로그인하고 ${missing ? `충전소 ${station.station_id}` : name} 즐겨찾기`}
            className="shrink-0 rounded-full p-2 text-ink-3 transition-colors hover:bg-canvas"
          >
            <StarIcon filled={false} />
          </Link>
        ) : null}
      </div>
    </li>
  );
}

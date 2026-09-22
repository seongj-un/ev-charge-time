"use client";

import { useEffect, useRef } from "react";

import type { Station } from "@/lib/api/types";

import { toMapPoints } from "./map-view";

/**
 * 충전소 지도.
 *
 * **키가 필요한 SDK를 쓰지 않는다.** Leaflet + OpenStreetMap은 인증키도
 * 도메인 등록도 없다. 지금 외부 키 세 개(충전소·기상청·Gemini)가 없으면 각
 * 기능이 501이 되는데, 시연 전에 네 번째 실패 지점을 만들 이유가 없다.
 * 나중에 Kakao 지도로 바꾸고 싶으면 이 파일만 갈아끼우면 된다.
 *
 * Leaflet은 `window`를 직접 만지므로 서버에서 불러오면 터진다. 그래서 모듈을
 * 이펙트 안에서 동적으로 가져온다 — 서버 렌더에는 빈 상자만 나간다.
 */

type Props = {
  center: { lat: number; lng: number };
  stations: Station[] | null;
  /** 지도 자리의 높이. 모바일과 데스크톱이 다르다. */
  className?: string;
};

export function StationMap({ center, stations, className = "" }: Props) {
  const holder = useRef<HTMLDivElement>(null);
  /* Leaflet 인스턴스는 렌더와 무관하다. state에 두면 매번 지도를 다시 그린다. */
  const map = useRef<{ remove: () => void } | null>(null);
  const layer = useRef<{ clearLayers: () => void } | null>(null);

  useEffect(() => {
    let alive = true;
    let cleanup: (() => void) | undefined;

    void (async () => {
      const L = (await import("leaflet")).default;
      if (!alive || !holder.current || map.current) return;

      const instance = L.map(holder.current, {
        center: [center.lat, center.lng],
        zoom: 15,
        // 스크롤로 페이지를 내리다 지도가 확대되면 목록을 읽던 사람이 길을 잃는다.
        scrollWheelZoom: false,
      });

      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(instance);

      map.current = instance;
      layer.current = L.layerGroup().addTo(instance);
      cleanup = () => {
        instance.remove();
        map.current = null;
        layer.current = null;
      };
    })();

    return () => {
      alive = false;
      cleanup?.();
    };
    // 지도는 한 번만 만든다. 기준점 이동은 아래 이펙트가 맡는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* 기준점이 바뀌면(내 위치 ↔ 지역) 그쪽으로 옮긴다. */
  useEffect(() => {
    const instance = map.current as { setView?: (c: [number, number], z: number) => void } | null;
    instance?.setView?.([center.lat, center.lng], 15);
  }, [center.lat, center.lng]);

  /* 목록이 바뀌면 표시를 다시 찍는다. */
  useEffect(() => {
    let alive = true;
    void (async () => {
      const L = (await import("leaflet")).default;
      const group = layer.current as { clearLayers: () => void; addLayer: (l: unknown) => void } | null;
      if (!alive || !group) return;

      group.clearLayers();
      group.addLayer(
        L.circleMarker([center.lat, center.lng], {
          radius: 7,
          color: "#0c5949",
          fillColor: "#0c5949",
          fillOpacity: 1,
          weight: 3,
        }).bindPopup("찾는 기준점"),
      );

      for (const point of toMapPoints(stations ?? [])) {
        group.addLayer(
          L.circleMarker([point.lat, point.lng], {
            radius: 6,
            /*
             * 색만으로 알리지 않는다 — 팝업에 글자로도 적는다. 차트에서
             * 부하구간을 색·글자·표로 세 번 말한 것과 같은 원칙이다.
             */
            color: "#fefefe",
            fillColor: point.available ? "#2f7c5a" : "#7c7d80",
            fillOpacity: 1,
            weight: 2,
          }).bindPopup(
            `<strong>${escapeHtml(point.name)}</strong><br>${
              point.available ? "사용 가능한 충전기 있음" : "지금 사용 가능한 충전기 없음"
            }`,
          ),
        );
      }
    })();
    return () => {
      alive = false;
    };
  }, [stations, center.lat, center.lng]);

  return (
    <div
      ref={holder}
      className={`overflow-hidden rounded-card border border-line bg-sunken ${className}`}
      // 지도는 목록과 같은 정보를 보여준다. 목록이 이미 읽히므로 중복해 읽히지 않게 한다.
      role="img"
      aria-label="충전소 위치 지도"
    />
  );
}

/** 충전소 이름이 팝업 HTML에 그대로 들어간다. 외부 API가 준 문자열이다. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

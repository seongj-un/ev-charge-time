"use client";

import { useId, useState } from "react";

import { formatPricePerKwh } from "@/lib/format";

import { BAND_KEY_LABEL, BAND_COLOR, type BandKey } from "./bands";

/**
 * 시간별 단가 막대 차트. 하루 단가 화면과 추천 결과 화면이 같은 것을 쓴다.
 *
 * 축은 0–23시로 고정하지 않는다. 추천 결과는 "18시 → 다음날 08시"처럼
 * 자정을 넘는 구간을 그린다. 그래서 컬럼 목록을 통째로 받는다.
 *
 * 막대 높이는 0을 바닥으로 단가에 비례한다. 잘린 축을 쓰면 71.2원과 113.0원이
 * 몇 배 차이처럼 보인다 — 절감액을 주장하는 화면에서 그건 과장이다.
 *
 * 색 접근성: 부하구간 색 4개는 색맹 분리(ΔE 12.5–17.5)는 통과하지만, 중간부하와
 * 주말 할인은 흰 배경 대비가 3:1 아래다. 그래서 색만으로 정보를 주지 않는다 —
 * 범례, 막대마다 읽히는 레이블, 아래 단가 표가 같은 정보를 글자로 가지고 있다.
 */

export type PriceColumn = {
  /** 0–23 */
  hour: number;
  bandKey: BandKey;
  pricePerKwh: number;
};

export type ChartMarker = {
  /** 이 마커가 덮는 시각들 */
  hours: number[];
  tone: "ink" | "muted";
  label: string;
};

type Props = {
  columns: PriceColumn[];
  markers?: ChartMarker[];
  /** x축 눈금을 몇 칸마다 찍을지. 좁은 화면에서 라벨이 겹치지 않게 한다. */
  labelEvery?: number;
  /** 막대 영역 높이 (px) */
  plotHeight?: number;
  className?: string;
};

const MARKER_TONE = {
  ink: "bg-ink",
  muted: "bg-ink-3/45",
} as const;

export function PriceBarChart({
  columns,
  markers = [],
  labelEvery = 1,
  plotHeight = 200,
  className = "",
}: Props) {
  const tableId = useId();
  const [hovered, setHovered] = useState<number | null>(null);

  if (columns.length === 0) return null;

  const maxPrice = Math.max(...columns.map((column) => column.pricePerKwh));

  return (
    <figure className={`relative ${className}`}>
      {/* 마커 줄 — 막대 위에 얹히는 "추천"·"지금 바로" 구간 표시 */}
      {markers.length > 0 ? (
        <div className="mb-2 flex flex-col gap-1">
          {markers.map((marker) => (
            <div key={marker.label} className="flex gap-[2px]" aria-hidden>
              {columns.map((column, index) => (
                <div key={index} className="flex-1">
                  {marker.hours.includes(column.hour) ? (
                    <div className={`h-[3px] rounded-full ${MARKER_TONE[marker.tone]}`} />
                  ) : (
                    <div className="h-[3px]" />
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      {/* 막대 */}
      <div className="flex items-end gap-[2px]" style={{ height: plotHeight }}>
        {columns.map((column, index) => {
          const ratio = maxPrice > 0 ? column.pricePerKwh / maxPrice : 0;
          const label = `${column.hour}시 · ${BAND_KEY_LABEL[column.bandKey]} · ${formatPricePerKwh(column.pricePerKwh)}원/kWh`;
          return (
            <div
              key={index}
              className="relative flex h-full flex-1 items-end"
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            >
              <button
                type="button"
                aria-label={label}
                onFocus={() => setHovered(index)}
                onBlur={() => setHovered(null)}
                className="w-full rounded-t-[3px] transition-opacity focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                style={{
                  height: `${Math.max(ratio * 100, 2)}%`,
                  background: BAND_COLOR[column.bandKey],
                  opacity: hovered === null || hovered === index ? 1 : 0.55,
                }}
              />
              {hovered === index ? (
                // 같은 내용이 버튼의 접근명에 이미 들어 있다. 두 번 읽히지 않게 숨긴다.
                <div
                  aria-hidden
                  data-chart-tooltip
                  className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-ink px-2.5 py-1.5 text-xs font-bold text-white shadow-lg"
                >
                  <span className="tnum">{column.hour}시</span> ·{" "}
                  {BAND_KEY_LABEL[column.bandKey]} ·{" "}
                  <span className="tnum">{formatPricePerKwh(column.pricePerKwh)}</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* x축 */}
      <div className="mt-2 border-t border-line pt-1.5">
        <div className="flex gap-[2px]">
          {columns.map((column, index) => (
            <div
              key={index}
              className="tnum flex-1 text-center text-[11px] text-ink-3"
            >
              {index % labelEvery === 0 ? column.hour : ""}
            </div>
          ))}
        </div>
      </div>

      {/* 스크린리더와 "표로 보기"를 위한 같은 데이터. 대비가 낮은 색을 글자가 받친다. */}
      <table id={tableId} className="sr-only">
        <caption>시간별 단가 (원/kWh)</caption>
        <thead>
          <tr>
            <th scope="col">시각</th>
            <th scope="col">부하구간</th>
            <th scope="col">단가</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((column, index) => (
            <tr key={index}>
              <th scope="row">{column.hour}시</th>
              <td>{BAND_KEY_LABEL[column.bandKey]}</td>
              <td>{formatPricePerKwh(column.pricePerKwh)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** 차트 범례. 색만으로 구분하지 않도록 차트와 항상 함께 둔다. */
export function BandLegend({
  keys,
  markers = [],
  className = "",
}: {
  keys: BandKey[];
  markers?: { label: string; tone: "ink" | "muted" }[];
  className?: string;
}) {
  return (
    <ul className={`flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-2 ${className}`}>
      {keys.map((key) => (
        <li key={key} className="flex items-center gap-1.5">
          <span
            className="size-2.5 rounded-[3px]"
            style={{ background: BAND_COLOR[key] }}
            aria-hidden
          />
          {BAND_KEY_LABEL[key]}
        </li>
      ))}
      {markers.map((marker) => (
        <li key={marker.label} className="flex items-center gap-1.5">
          <span
            className={`h-[3px] w-4 rounded-full ${MARKER_TONE[marker.tone]}`}
            aria-hidden
          />
          {marker.label}
        </li>
      ))}
    </ul>
  );
}

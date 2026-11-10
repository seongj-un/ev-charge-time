"use client";

import { useEffect, useState } from "react";

import type { BandKey } from "@/components/chart/bands";
import {
  BandLegend,
  PriceBarChart,
  type ChartMarker,
  type PriceColumn,
} from "@/components/chart/PriceBarChart";
import { SolarOverlay } from "@/components/chart/SolarOverlay";
import { Card } from "@/components/ui/Card";
import { motionDelay } from "@/lib/motion";

import { axisRangeLabel, type Axis, type SolarRow } from "./chart-data";

/**
 * "충전 가능 시간의 단가" 카드.
 *
 * 범례 자리가 모바일(차트 아래)과 데스크톱(제목 오른쪽)에서 다른데, 두 번 그리지 않고
 * grid 배치로 옮긴다. 범례를 두 벌 그리면 스크린리더가 "경부하 중간 최대 추천 지금 바로"를
 * 두 번 읽는다.
 */

/** 부하구간 범례 순서. 값이 도는 순서(경→중→최대)와 맞춰 둔다. */
const BAND_ORDER: BandKey[] = ["light", "middle", "peak", "flat", "discounted"];

export function PriceChartCard({
  axis,
  columns,
  markers,
  solar = null,
}: {
  axis: Axis;
  columns: PriceColumn[];
  markers: ChartMarker[];
  /** 단가 막대 아래 태양광 막대. 없으면 줄을 그리지 않는다. */
  solar?: SolarRow | null;
}) {
  const desktop = useIsDesktop();

  // 실제로 나타난 구간만 범례에 올린다. 안 쓰인 색을 설명하면 차트에 없는 것을 찾게 된다.
  const presentKeys = BAND_ORDER.filter((key) =>
    columns.some((column) => column.bandKey === key),
  );

  return (
    <Card className="motion-rise mt-4 p-4 lg:mt-6 lg:p-7" style={motionDelay(120)}>
      <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-center lg:gap-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2 lg:col-start-1 lg:row-start-1">
          <h2 className="text-base font-bold lg:text-lg">
            충전 가능 시간<span className="hidden lg:inline">의 단가</span>
          </h2>
          <span className="tnum text-sm text-ink-2">{axisRangeLabel(axis)}</span>
        </div>

        <div className="order-last lg:order-none lg:col-start-2 lg:row-start-1 lg:justify-self-end">
          <BandLegend
            keys={presentKeys}
            // 범례는 "추천"을 먼저 읽힌다 (디자인 순서). 차트 마커 줄은 "지금 바로"가
            // 위에 오도록 둔 채라, 여기서만 순서를 뒤집는다.
            markers={[...markers]
              .reverse()
              .map((marker) => ({ label: marker.label, tone: marker.tone }))}
          />
        </div>

        <div className="lg:col-span-2 lg:row-start-2">
          <PriceBarChart
            columns={columns}
            markers={markers}
            // 좁은 화면에 눈금을 다 찍으면 숫자가 서로 겹쳐 읽히지 않는다.
            labelEvery={desktop ? 1 : 4}
            plotHeight={desktop ? 190 : 116}
          />
          {solar ? (
            /*
             * 단가 막대와 같은 칸 폭으로 바로 아래에 둔다. 같은 y축에 올리지 않는 이유는
             * SolarOverlay 주석 참고 — 단위가 달라 이중축이 되면 높이를 마음대로 과장할 수 있다.
             * 추천 계산에는 들어가지 않은 참고 정보라는 점을 제목에서 밝힌다.
             */
            <div className="mt-4 border-t border-line pt-3">
              <p className="text-sm font-bold">
                태양광 발전 예측 <span className="font-normal text-ink-2">· 전남 · 참고용</span>
              </p>
              <SolarOverlay
                className="mt-2"
                hours={solar.hours}
                columns={columns.map((column) => column.hour)}
                assumptions={
                  solar.partial
                    ? [...solar.assumptions, "기상청 예보가 아직 없는 날짜의 시각은 비워 두었습니다"]
                    : solar.assumptions
                }
              />
            </div>
          ) : null}
        </div>
      </div>

      <p className="mt-3 text-sm text-ink-2">단가 단위: 원/kWh · 부가 요금 제외</p>
    </Card>
  );
}

/**
 * 차트에 넘길 눈금 간격·높이만 화면 폭에 따라 바꾼다.
 *
 * CSS로 못 하는 이유는 둘 다 컴포넌트 prop이기 때문이다. 차트를 모바일용·데스크톱용
 * 두 번 그려 하나를 숨기는 방법도 있지만, 그러면 같은 막대 14개가 DOM에 두 벌 생기고
 * 스크린리더용 단가 표도 두 번 읽힌다.
 *
 * 서버 렌더와 첫 페인트는 모바일 값으로 간다 (모바일 우선). matchMedia가 없는 환경
 * (jsdom 등)에서도 그대로 모바일 값이다.
 */
function useIsDesktop(): boolean {
  const [desktop, setDesktop] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    // globals.css의 lg 분기점과 같은 값이어야 범례 위치와 눈금 간격이 같이 바뀐다.
    const query = window.matchMedia("(min-width: 64rem)");
    const sync = () => setDesktop(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return desktop;
}

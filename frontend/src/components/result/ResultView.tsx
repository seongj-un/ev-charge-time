"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ChartMarker } from "@/components/chart/PriceBarChart";
import { PageBody, PageContainer } from "@/components/shell/AppShell";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { fetchRecommendation, fetchSolarForecast, fetchTimeline } from "@/lib/api/endpoints";
import type { RecommendResponse, SolarForecast } from "@/lib/api/types";
import { fromSearchParams, toRecommendRequest, type RecommendForm } from "@/lib/recommend-params";

import {
  axisHours,
  bandSummary,
  buildAxis,
  buildColumns,
  buildSolarHours,
  type Axis,
  type SolarRow,
} from "./chart-data";
import { unverifiedNotice } from "@/lib/tariff";

import { assumptionsSentence } from "./plan-text";
import { PlanCards } from "./PlanCards";
import { PriceChartCard } from "./PriceChartCard";
import { ResultActions } from "./ResultActions";
import { ResultHeader } from "./ResultHeader";
import { NoConditionState, ResultErrorState, ResultSkeleton } from "./ResultStates";

/**
 * 추천 결과 화면.
 *
 * 조건은 URL 쿼리로 들어온다 (recommend-params.ts). 그래서 이 컴포넌트는 라우터를
 * 몰라도 되고, 쿼리 문자열 하나만 받아서 전부 스스로 판단한다 — 테스트에서
 * 라우터를 흉내 낼 일이 없다.
 *
 * 요청이 두 종류라 상태도 둘로 나눠 둔다.
 *   추천(POST /api/recommend)  — 이게 없으면 화면이 없다
 *   단가(GET /api/timeline)    — 차트를 그리는 데만 쓴다
 * 단가를 못 받았다고 추천 시각과 금액까지 감추면, 멀쩡히 계산된 답을 버리는 것이다.
 */

type PlanState =
  | { status: "loading" }
  | { status: "ready"; response: RecommendResponse }
  | { status: "error"; message: string };

type ChartState =
  | { status: "loading" }
  | {
      status: "ready";
      axis: Axis;
      columns: ReturnType<typeof buildColumns>;
      /** 단가 차트 아래 태양광 막대. 예보를 하나도 못 받으면 null — 막대 줄 자체를 그리지 않는다. */
      solar: SolarRow | null;
    }
  | { status: "error" };

/** 하루 단가 화면과 같은 지역. 데이터가 전남·광주만 있다. */
const SOLAR_REGION = "전남";

/** 어느 요청에 대한 결과인지를 결과와 함께 들고 다닌다. */
type Loaded = { key: string; plan: PlanState; chart: ChartState };

export function ResultView({ query }: { query: string }) {
  const form = useMemo(() => fromSearchParams(new URLSearchParams(query)), [query]);
  // "다시 시도"가 같은 조건으로 요청을 한 번 더 내보내게 하는 값.
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const requestKey = `${attempt}:${query}`;

  const [loaded, setLoaded] = useState<Loaded | null>(null);

  /*
   * 조건이 바뀌면 이전 조건의 결과가 한 프레임이라도 보이면 안 된다 (22:00 추천을
   * 보다가 조건을 바꿨는데 옛 금액이 새 조건 배지 옆에 남는 식).
   * 효과에서 setState로 되돌리는 대신, 결과에 요청 키를 붙여 두고 렌더에서 맞춰 본다 —
   * 키가 다르면 그냥 "불러오는 중"이다. 여분의 렌더도, 그 사이의 빈틈도 없다.
   */
  const current = loaded?.key === requestKey ? loaded : null;
  const plan: PlanState = current?.plan ?? { status: "loading" };
  const chart: ChartState = current?.chart ?? { status: "loading" };

  useEffect(() => {
    if (!form) return;

    // 응답이 늦게 도착했을 때 이미 지나간 조건의 결과를 그리지 않게 한다.
    let cancelled = false;

    void (async () => {
      let response: RecommendResponse;
      try {
        response = await fetchRecommendation(toRecommendRequest(form));
      } catch (error) {
        // ApiError.message는 이미 사람이 읽을 문장이다 (client.ts에서 만든다).
        if (!cancelled) {
          setLoaded({
            key: requestKey,
            plan: { status: "error", message: messageOf(error) },
            chart: { status: "error" },
          });
        }
        return;
      }
      if (cancelled) return;

      // 추천부터 먼저 그린다. 단가를 기다리느라 추천 시각을 늦게 보여줄 이유가 없다.
      setLoaded({
        key: requestKey,
        plan: { status: "ready", response },
        chart: { status: "loading" },
      });

      const axis = buildAxis({
        earliestStart: form.earliestStart,
        deadline: form.deadline,
        bestStart: response.best.start,
        bestEnd: response.best.end,
      });

      const next: ChartState = axis
        ? await loadChart(axis, form)
        : { status: "error" };
      if (cancelled) return;
      // 그 사이 조건이 바뀌었으면 옛 차트를 새 결과에 얹지 않는다.
      setLoaded((prev) => (prev?.key === requestKey ? { ...prev, chart: next } : prev));
    })();

    return () => {
      cancelled = true;
    };
  }, [form, requestKey]);

  if (!form) {
    return (
      <PageContainer className="pb-10">
        <NoConditionState />
      </PageContainer>
    );
  }

  const response = plan.status === "ready" ? plan.response : null;
  const unverifiedItems = response?.unverified_tariff_items ?? [];
  const assumptions = response ? assumptionsSentence(response.assumptions) : null;

  const columns = chart.status === "ready" ? chart.columns : [];

  /*
   * 차트 위에 얹히는 두 구간. 날짜를 지운 시각만 넘기면 축이 다음날로 밀렸을 때
   * 오늘 밤 "지금 바로"가 다음날 같은 시각 막대에 얹힌다 — 그래서 축 기준으로 센다.
   * 축이 아직 없으면 그릴 막대도, 읽어 낼 부하구간도 없다.
   */
  const axis = chart.status === "ready" ? chart.axis : null;
  const baselineHours =
    response && axis ? axisHours(axis, response.baseline_now.start, response.baseline_now.end) : [];
  const bestHours = response && axis ? axisHours(axis, response.best.start, response.best.end) : [];
  // 축에 한 칸도 안 걸친 구간은 마커에서 뺀다. 범례가 차트에 없는 표시를 설명하면
  // 사용자는 없는 것을 찾는다.
  const markers: ChartMarker[] = (
    [
      { hours: baselineHours, tone: "muted", label: "지금 바로" },
      { hours: bestHours, tone: "ink", label: "추천" },
    ] satisfies ChartMarker[]
  ).filter((marker) => marker.hours.length > 0);

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto w-full max-w-[1280px] px-5 py-5 sm:px-6 lg:px-8 lg:py-8">
          <ResultHeader form={form} query={query} unverified={unverifiedItems.length > 0} />
        </div>
      </section>

      <PageBody className="pb-10">
      {plan.status === "loading" ? <ResultSkeleton /> : null}

      {plan.status === "error" ? (
        <ResultErrorState message={plan.message} query={query} onRetry={retry} />
      ) : null}

      {response ? (
        <>
          <PlanCards
            form={form}
            response={response}
            // 부하구간은 응답에 없다. 받아 온 단가에서 읽어 내고, 단가가 없으면 말하지 않는다.
            bestBand={bandSummary(columns, bestHours)}
            baselineBand={bandSummary(columns, baselineHours)}
          />

          {chart.status === "ready" && columns.length > 0 ? (
            <PriceChartCard
              axis={chart.axis}
              columns={columns}
              markers={markers}
              solar={chart.solar}
            />
          ) : null}

          {chart.status === "error" ? (
            <p className="mt-3 text-sm text-ink-2 lg:mt-5">
              시간대별 단가를 불러오지 못했습니다. 위 추천 시각과 금액은 그대로입니다.
            </p>
          ) : null}

          {/*
            확인 전 요금 항목이 있으면 반드시 띄운다. 접거나 숨기는 옵션을 두지 않는 건
            의도된 것이다 — 이 줄이 사라지는 순간 위의 2,373원이 확정 금액처럼 읽힌다.
          */}
          {unverifiedItems.length > 0 ? (
            <Notice className="mt-4 lg:mt-5">
              <strong className="font-bold">요금 일부 확인 중</strong> ·{" "}
              {unverifiedNotice(unverifiedItems)}
              {/*
                어느 항목이 확인 전인지는 백엔드가 키로 알려준다 (`adders.fuel_adjustment_per_kwh` 등).
                문장에 그대로 이어 붙이면 아무도 안 읽으므로 접어 두되, 버리지는 않는다 —
                "어디가 잠정치냐"는 질문에 답할 수 있어야 한다.
              */}
              <details className="mt-1.5">
                <summary className="cursor-pointer text-sm font-bold">
                  확인 전 항목 <span className="tnum">{unverifiedItems.length}</span>건
                </summary>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
                  {unverifiedItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </details>
            </Notice>
          ) : null}

          {assumptions ? (
            <p className="mt-4 text-sm leading-relaxed text-ink-2">{assumptions}</p>
          ) : null}

          <ResultActions />
        </>
      ) : null}
      </PageBody>
    </>
  );
}

/**
 * 축이 걸친 날짜마다 단가를 받아 컬럼으로 만든다.
 *
 * 자정을 넘으면 날짜가 둘이다. 계절·휴일·주말 할인이 날짜마다 달라서 첫날 요금표를
 * 둘째 날에 재활용하면 금요일 밤 요금으로 토요일 새벽을 그리게 된다.
 */
async function loadChart(axis: Axis, form: RecommendForm): Promise<ChartState> {
  // 공공 급속은 사업자마다 단가가 달라, 기본 설정의 백엔드는 단가 없이 timeline을
  // 거절한다(422). 추천 요청에 실은 값을 단가 요청에도 똑같이 실어야 차트가 나온다.
  const publicBasePrice = form.mode === "public_fast" ? form.publicBasePrice : undefined;
  // 태양광은 단가와 함께 받되, 실패해도 단가 차트는 그린다. 덤 정보가 본 정보를 막으면 안 된다.
  const solarPromise = loadSolar(axis);
  try {
    const timelines = await Promise.all(
      axis.days.map((day) => fetchTimeline({ day, mode: form.mode, publicBasePrice })),
    );
    return {
      status: "ready",
      axis,
      columns: buildColumns(axis, timelines),
      solar: await solarPromise,
    };
  } catch {
    return { status: "error" };
  }
}

/**
 * 축이 걸친 날짜마다 태양광 예측을 받는다.
 *
 * 기상청 단기예보는 약 2일 앞까지라 먼 날짜는 422로 거절된다. 날짜 하나가 실패했다고
 * 전부 버리지 않고 받은 날만 쓴다. 하나도 못 받으면(키 없음 501 포함) null.
 */
async function loadSolar(axis: Axis): Promise<SolarRow | null> {
  const settled = await Promise.allSettled(
    axis.days.map((day) => fetchSolarForecast({ region: SOLAR_REGION, day })),
  );
  const forecasts = settled
    .filter((item): item is PromiseFulfilledResult<SolarForecast> => item.status === "fulfilled")
    .map((item) => item.value);
  if (forecasts.length === 0) return null;
  const hours = buildSolarHours(axis, forecasts);
  if (hours.length === 0) return null;
  return {
    hours,
    assumptions: forecasts[0].assumptions,
    partial: forecasts.length < axis.days.length,
  };
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "추천을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

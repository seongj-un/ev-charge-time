"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { BAND_COLOR, BAND_KEY_LONG_LABEL } from "@/components/chart/bands";
import { ArrowRightIcon } from "@/components/shell/icons";
import { todayInSeoul } from "@/components/timeline/timeline-view";
import { fetchTimeline } from "@/lib/api/endpoints";
import { MODE_LABEL, SEASON_LABEL, type TimelineResponse } from "@/lib/api/types";
import { formatKoreanDate, formatPricePerKwh } from "@/lib/format";
import { motionDelay } from "@/lib/motion";

import { formatRun, hourInSeoul, summarizeDay } from "./today-view";

type State =
  | { status: "loading" }
  | { status: "ready"; timeline: TimelineResponse; hour: number }
  | { status: "error" };

/**
 * 홈 머리의 '오늘 요금' 판. 실제 GET /api/timeline 응답으로 그린다.
 *
 * 이전 홈은 "예시" 라벨을 단 고정 카드였다 — 조건 없이 추천 금액을 지어내면 내 차 기준으로
 * 읽히기 때문이었다. 오늘의 시간대별 단가는 조건 없이도 참인 사실이라 실데이터로 보여줄 수
 * 있고, 서비스가 무엇을 보는지가 첫 화면에서 바로 드러난다. 기준(자가 저압)은 판에 적는다.
 */
export function TodayPanel() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchTimeline({ day: todayInSeoul(), mode: "self_low" })
      .then((timeline) => {
        if (!cancelled) setState({ status: "ready", timeline, hour: hourInSeoul() });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="rounded-panel border border-line bg-surface p-5 text-ink shadow-panel sm:p-6 lg:p-7">
      {state.status === "loading" ? <PanelSkeleton /> : null}
      {state.status === "error" ? <PanelError /> : null}
      {state.status === "ready" ? <PanelReady timeline={state.timeline} hour={state.hour} /> : null}
    </div>
  );
}

function PanelReady({ timeline, hour }: { timeline: TimelineResponse; hour: number }) {
  const summary = summarizeDay(timeline.hours);
  if (!summary) return <PanelError />;

  const now = summary.cells.find((cell) => cell.hour === hour) ?? summary.cells[0];
  const dayKind = timeline.is_holiday ? "휴일" : "평일";

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-bold">오늘 전기차 충전 요금</h2>
        <p className="text-sm font-bold text-ink-2">
          {formatKoreanDate(timeline.day)} · {SEASON_LABEL[timeline.season]} {dayKind}
        </p>
      </div>

      <div className="mt-5 flex items-end justify-between gap-4">
        <div>
          <p className="text-sm font-bold text-ink-2">
            지금 <span className="tnum">{String(now.hour).padStart(2, "0")}</span>시
          </p>
          <p className="mt-1 flex items-baseline gap-1.5">
            <span className="tnum text-figure lg:text-[48px]">{formatPricePerKwh(now.price)}</span>
            <span className="text-sm font-bold text-ink-2">원/kWh</span>
          </p>
        </div>
        <span
          className="inline-flex items-center gap-1.5 rounded-pill px-3 py-1.5 text-sm font-bold"
          // 중간부하(호박색)·할인(라임) 위의 흰 글자는 대비가 모자라 검정 글자를 쓴다.
          style={{
            background: BAND_COLOR[now.bandKey],
            color: now.bandKey === "light" || now.bandKey === "peak" ? "#ffffff" : "var(--color-ink)",
          }}
        >
          {BAND_KEY_LONG_LABEL[now.bandKey]}
        </span>
      </div>

      <DayStrip cells={summary.cells} nowHour={now.hour} />

      <dl className="mt-6 grid grid-cols-2 gap-3">
        <div className="rounded-card bg-brand-soft p-4">
          <dt className="text-sm font-bold text-ink-2">가장 싼 시간</dt>
          <dd className="mt-1.5 text-base font-bold">
            {summary.cheapest.map(formatRun).join(", ")}
          </dd>
          <dd className="tnum mt-0.5 text-sm font-bold text-band-light">
            {formatPricePerKwh(summary.minPrice)}원/kWh
          </dd>
        </div>
        <div className="rounded-card bg-sunken p-4">
          <dt className="text-sm font-bold text-ink-2">가장 비싼 시간</dt>
          <dd className="mt-1.5 text-base font-bold">
            {summary.priciest.map(formatRun).join(", ")}
          </dd>
          <dd className="tnum mt-0.5 text-sm font-bold text-band-peak">
            {formatPricePerKwh(summary.maxPrice)}원/kWh
          </dd>
        </div>
      </dl>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p className="text-sm text-ink-2">
          {MODE_LABEL[timeline.mode]} 기준 · 같은 날에도{" "}
          <strong className="tnum font-bold text-ink">{summary.ratio.toFixed(1)}배</strong> 차이
        </p>
        <Link
          href="/timeline"
          className="inline-flex min-h-11 items-center gap-1 rounded-field text-sm font-bold text-brand underline-offset-4 hover:underline
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          하루 단가 자세히
          <ArrowRightIcon className="size-4" />
        </Link>
      </div>
    </>
  );
}

/**
 * 24칸 띠. 한 칸이 한 시간이고 색이 부하구간이다. 지금 시각 칸 위에 라임 표시를 단다.
 * 숫자 표가 아니라 '하루의 모양'을 보여주는 그림이라 스크린리더에는 요약 문장 하나만 준다.
 */
function DayStrip({
  cells,
  nowHour,
}: {
  cells: { hour: number; bandKey: keyof typeof BAND_COLOR }[];
  nowHour: number;
}) {
  return (
    <figure className="mt-6">
      <div className="relative" aria-hidden>
        <div className="grid grid-cols-24 gap-[3px]">
          {cells.map((cell, index) => (
            <div key={cell.hour} className="relative h-12 lg:h-14">
              <div
                className={`motion-grow h-full rounded-[4px] ${cell.hour === nowHour ? "ring-2 ring-ink ring-offset-2 ring-offset-surface" : ""}`}
                style={{ background: BAND_COLOR[cell.bandKey], ...motionDelay(160 + index * 18) }}
              />
            </div>
          ))}
        </div>
        <div className="tnum mt-2 grid grid-cols-4 text-xs font-bold text-ink-2">
          <span>0시</span>
          <span>6시</span>
          <span>12시</span>
          <span className="flex justify-between">
            18시<span>24시</span>
          </span>
        </div>
      </div>
      <figcaption className="sr-only">
        오늘 24시간의 부하구간 띠. 지금은 {nowHour}시입니다.
      </figcaption>
    </figure>
  );
}

function PanelSkeleton() {
  return (
    <div aria-busy="true" aria-label="오늘 요금을 불러오는 중">
      <div className="h-6 w-48 animate-pulse rounded-lg bg-sunken" />
      <div className="mt-6 h-14 w-56 animate-pulse rounded-lg bg-sunken" />
      <div className="mt-6 h-14 animate-pulse rounded-lg bg-sunken lg:h-16" />
      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="h-[92px] animate-pulse rounded-card bg-sunken" />
        <div className="h-[92px] animate-pulse rounded-card bg-sunken" />
      </div>
      <div className="mt-5 h-11 animate-pulse rounded-lg bg-sunken" />
    </div>
  );
}

function PanelError() {
  return (
    <div className="flex min-h-[320px] flex-col items-start justify-center gap-3" role="status">
      <h2 className="text-base font-bold">오늘 요금을 불러오지 못했어요</h2>
      <p className="text-sm text-ink-2">
        서버에 잠시 닿지 않아요. 하루 단가 화면에서 다시 시도할 수 있어요.
      </p>
      <Link
        href="/timeline"
        className="inline-flex min-h-11 items-center gap-1 text-sm font-bold text-brand underline underline-offset-4"
      >
        하루 단가 보기
        <ArrowRightIcon className="size-4" />
      </Link>
    </div>
  );
}

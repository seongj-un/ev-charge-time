"use client";

import { useEffect, useState } from "react";

import { BandLegend, PriceBarChart } from "@/components/chart/PriceBarChart";
import { SolarOverlay } from "@/components/chart/SolarOverlay";
import { PageContainer } from "@/components/shell/AppShell";
import { Badge } from "@/components/ui/Badge";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ApiError } from "@/lib/api/client";
import { fetchHealth, fetchSolarForecast, fetchTimeline } from "@/lib/api/endpoints";
import {
  MODE_LABEL,
  type Mode,
  type SolarForecast,
  type TimelineResponse,
} from "@/lib/api/types";
import { unverifiedNotice } from "@/lib/tariff";

import { DayStepper } from "./DayStepper";
import { useIsDesktop, useIsHydrated } from "./hooks";
import { DiscountBanner } from "./DiscountBanner";
import { PriceListCard } from "./PriceListCard";
import { SolarOverlayButton } from "./SolarOverlayButton";
import {
  MODE_OPTIONS,
  bandPriceRows,
  cheapestHours,
  daySubtitle,
  discountRangeLabel,
  discountScopeLabel,
  hasDiscount,
  isDay,
  parsePublicBasePrice,
  presentBandKeys,
  recommendHref,
  shiftDay,
  toColumns,
  todayInSeoul,
} from "./timeline-view";

/**
 * 하루 단가 화면 본체 (F-05·F-06).
 *
 * URL 쿼리와 떼어 놓은 이유: 이 컴포넌트가 지켜야 하는 건 "응답에 있는 것만 보여준다"인데,
 * next/navigation을 안에서 부르면 그걸 확인하려고 라우터부터 흉내 내야 한다.
 * 쿼리 읽고 쓰는 일은 TimelinePage가 하고, 여기는 날짜·방식을 값으로만 받는다.
 */

type Load =
  | { status: "loading" }
  | { status: "ready"; data: TimelineResponse }
  | { status: "error"; message: string };

const MARKER_LABEL = "최저 단가";

/** 대회가 빛가람(나주)이라 전남으로 고정한다. 지역 선택을 넣으면 상태로 올린다. */
const SOLAR_REGION = "전남";

export function TimelineScreen({
  initialDay,
  initialMode = "self_low",
  initialPublicBasePrice,
  onQueryChange,
}: {
  /** URL의 ?day=. 없으면 마운트 뒤에 오늘로 채운다. */
  initialDay?: string | null;
  initialMode?: Mode;
  /** URL의 ?public_base_price=. 공용 급속 단가 칸에 그대로 채운다. */
  initialPublicBasePrice?: string | null;
  /** 바뀐 날짜·방식(·공용 급속 단가)을 URL에 남기고 싶을 때 */
  onQueryChange?: (query: { day: string; mode: Mode; publicBasePrice?: number }) => void;
}) {
  /*
   * 첫 렌더에서 '오늘'을 정하지 않는다.
   *
   * 서버는 대개 UTC로 도는데 사용자는 KST다. 서버 렌더가 "10월 9일"을 그리고
   * 클라이언트가 "10월 10일"을 그리면 hydration 불일치가 나고, React는 그 자리를
   * 조용히 다시 그린다. 그래서 날짜가 URL에 있으면(= 서버와 클라이언트가 같은 값을 본다)
   * 그걸 쓰고, 없으면 hydration이 끝난 뒤에야 오늘을 계산한다.
   * 그 전까지 day는 null이고, 날짜 자리는 자리표시자라 서버 HTML에 날짜가 찍히지 않는다.
   *
   * dayOverride는 ◀▶로 옮긴 날짜다. URL 쿼리를 되받아 덮어쓰지 않는 이유는
   * TimelinePage가 router.replace를 쓰기 때문이다 — 날짜 이동은 히스토리를 만들지 않으니
   * "뒤로 가기로 이전 날짜" 같은 게 애초에 없고, 따라서 되돌려 받을 것도 없다.
   */
  const hydrated = useIsHydrated();
  const [dayOverride, setDayOverride] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>(initialMode);
  const day =
    dayOverride ?? (isDay(initialDay) ? initialDay : hydrated ? todayInSeoul() : null);

  /*
   * 공용 급속 단가. 공용 급속은 충전사업자마다 요금이 달라 공식 단가가 없고, 백엔드는
   * 단가 없이 오면 422로 "충전기에 적힌 요금을 넣어 달라"고 한다. 넣을 칸이 없으면
   * 사용자는 그 말을 들어도 할 수 있는 게 없다.
   *
   * 칸에는 친 글자를 그대로 들고, 보낼 값은 거기서 파생시킨다. 숫자로만 들고 있으면
   * "347."처럼 치는 도중의 글자가 사라진다. 알아볼 수 없는 값이면 단가 없이 부른다 —
   * 그러면 백엔드의 문장이 그대로 보이고, 그게 칸을 채우라는 안내가 된다.
   */
  const [priceInput, setPriceInput] = useState(initialPublicBasePrice ?? "");
  const publicBasePrice = mode === "public_fast" ? parsePublicBasePrice(priceInput) : null;

  /*
   * 요청 결과를 "어떤 요청의 결과인지"(requestKey)와 함께 들고 있는다.
   *
   * 로딩 여부를 따로 state로 두고 효과 안에서 setState하지 않는 게 요점이다. 그러면
   * 날짜를 바꾼 렌더와 로딩으로 바뀌는 렌더 사이에 옛 차트가 한 프레임 남고, 늦게 온
   * 응답이 새 날짜의 화면을 덮어쓸 자리도 생긴다. 지금 보고 있는 키와 결과의 키가
   * 다르면 그건 그냥 로딩이다 — 상태가 하나라 어긋날 수가 없다.
   */
  const [retryCount, setRetryCount] = useState(0);
  /**
   * 요금이 얼마나 확인됐는지. /health가 알려준다.
   *
   * 못 받으면 null로 둔다 — 단가 화면은 이것과 무관하게 서야 하고, 못 받았다고
   * "잠정치다"라고 단정하면 그것도 근거 없는 말이다.
   */
  const [tariffNote, setTariffNote] = useState<string | null>(null);

  /**
   * 태양광 예측. 버튼을 켤 때만 부른다 — 기상청 호출이라 늘 받아둘 이유가 없다.
   *
   * 지역은 지금 전남으로 고정한다. 대회가 빛가람(나주)이고 화면에 지역 선택이
   * 없다. 선택을 넣게 되면 이 상수를 상태로 올리면 된다.
   */
  const [solarOn, setSolarOn] = useState(false);
  /*
   * 예측도 단가처럼 "어느 날의 예측인지"(day)와 함께 들고 있는다.
   *
   * 날짜를 넘기면 새 날의 단가는 금방 오고 예보는 기상청을 거쳐 늦게 온다. 예측만
   * 덩그러니 들고 있으면 그 사이 어제의 일사량이 오늘 막대 위에 그려진다. 지금 날짜와
   * 예측의 날짜가 다르면 그건 그냥 "아직 안 왔다"다 — 단가의 requestKey와 같은 방식이다.
   */
  const [solar, setSolar] = useState<{ day: string; forecast: SolarForecast } | null>(null);
  /*
   * 실패는 두 갈래로 나눠 든다.
   *
   * 501은 백엔드에 기상청 키가 없다는 뜻이라 어느 날짜를 봐도 같다 — 버튼을 잠근다.
   * 그 밖의 실패(예보 범위 밖이라 422, 기상청 일시 오류)는 그 날 하루의 사정이다.
   * 한 번 실패했다고 기능 전체를 잠그면 오늘 예보도 다시는 못 본다. 그래서 실패한
   * 날짜만 적어 두고, 날짜가 바뀌면 저절로 풀리게 한다.
   */
  const [solarUnavailable, setSolarUnavailable] = useState(false);
  const [solarFailedDay, setSolarFailedDay] = useState<string | null>(null);

  useEffect(() => {
    if (!solarOn || day === null) return;
    let alive = true;
    fetchSolarForecast({ region: SOLAR_REGION, day })
      .then((forecast) => {
        if (alive) setSolar({ day, forecast });
      })
      .catch((error: unknown) => {
        // 켤 수 없으면 켜진 척하지 않는다 — 빈 오버레이가 "해가 없다"로 읽힌다.
        if (!alive) return;
        if (error instanceof ApiError && error.notImplemented) {
          setSolarUnavailable(true);
        } else {
          setSolarFailedDay(day);
        }
        setSolarOn(false);
      });
    return () => {
      alive = false;
    };
  }, [solarOn, day]);

  const solarForDay = solar !== null && solar.day === day ? solar.forecast : null;

  /*
   * 버튼 상태는 저장하지 않고 파생시킨다. 따로 들고 있으면 상태끼리 어긋나는
   * 경우(켜졌는데 loading, 꺼졌는데 ready 같은)를 손으로 막아야 한다.
   * 다시 누르면 solarOn이 켜지면서 loading이 먼저 잡히니 "불러오지 못함"이 남지 않는다.
   */
  const solarState: "ready" | "loading" | "unavailable" | "failed" = solarUnavailable
    ? "unavailable"
    : solarOn && solarForDay === null
      ? "loading"
      : !solarOn && solarFailedDay !== null && solarFailedDay === day
        ? "failed"
        : "ready";

  useEffect(() => {
    let alive = true;
    fetchHealth()
      .then((health) => {
        if (alive) setTariffNote(unverifiedNotice(health.unverified_tariff_items));
      })
      .catch(() => {
        if (alive) setTariffNote(null);
      });
    return () => {
      alive = false;
    };
  }, []);
  const [result, setResult] = useState<{ key: string; load: Load } | null>(null);
  // 단가도 키에 넣는다. 350원으로 받은 단가표를 400원을 친 화면에 보여주면 안 된다.
  const requestKey =
    day === null ? null : `${day}|${mode}|${publicBasePrice ?? ""}|${retryCount}`;
  const load: Load =
    requestKey !== null && result?.key === requestKey ? result.load : { status: "loading" };

  const isDesktop = useIsDesktop();

  useEffect(() => {
    if (day === null) return;
    const key = `${day}|${mode}|${publicBasePrice ?? ""}|${retryCount}`;
    let live = true;
    fetchTimeline({ day, mode, ...(publicBasePrice !== null ? { publicBasePrice } : {}) })
      .then((data) => {
        if (live) setResult({ key, load: { status: "ready", data } });
      })
      .catch((error: unknown) => {
        if (!live) return;
        // 백엔드가 준 문장을 그대로 쓴다. 우리가 고쳐 쓰면 무엇이 틀렸는지가 흐려진다.
        setResult({
          key,
          load: {
            status: "error",
            message:
              error instanceof ApiError ? error.message : "단가를 불러오지 못했습니다.",
          },
        });
      });
    return () => {
      live = false;
    };
  }, [day, mode, publicBasePrice, retryCount]);

  useEffect(() => {
    if (day === null) return;
    onQueryChange?.({ day, mode, ...(publicBasePrice !== null ? { publicBasePrice } : {}) });
  }, [day, mode, publicBasePrice, onQueryChange]);

  const data = load.status === "ready" ? load.data : null;
  const hours = data?.hours ?? [];
  const subtitle = data ? daySubtitle(data) : null;
  const discountRange = data ? discountRangeLabel(hours) : null;

  return (
    <PageContainer className="pb-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:gap-4">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-title text-ink lg:text-title-lg">
            하루 단가
          </h1>
          {/*
           * 모바일에서는 충전 방식이 배지다 (디자인 p-04). 좁은 화면에서 세그먼티드를
           * 제목 옆에 끼우면 셋 다 줄임표가 되고, 방식은 추천 화면에서 이미 고른 값이다.
           */}
          <span className="lg:hidden">
            <Badge tone="off">{MODE_LABEL[mode]}</Badge>
          </span>
        </div>

        <DayStepper
          day={day}
          subtitle={subtitle}
          onShift={(delta) => setDayOverride(day ? shiftDay(day, delta) : null)}
          className="lg:w-auto"
        />

        {/*
         * 래퍼 span으로 감싸는 이유: Tailwind가 내보내는 CSS에서 .hidden이 .inline-flex보다
         * 먼저 나온다. Badge가 이미 inline-flex라 className에 hidden을 더해도 안 숨겨진다.
         * 표시 속성을 다투지 않는 빈 태그에 걸어야 확실하다.
         */}
        {subtitle ? (
          <span className="hidden lg:block">
            <Badge tone="off">{subtitle}</Badge>
          </span>
        ) : null}

        <SegmentedControl
          name="timeline-mode"
          label="충전 방식"
          value={mode}
          options={MODE_OPTIONS.map((value) => ({ value, label: MODE_LABEL[value] }))}
          onChange={setMode}
          className="hidden lg:ml-auto lg:block lg:w-[360px] [&>legend]:sr-only"
        />
      </header>

      {/*
       * 모든 너비에서 보인다. 모바일에는 방식 선택이 없지만 URL로 공용 급속이 올 수 있고,
       * 그때 이 칸이 없으면 단가표를 볼 길이 없다.
       */}
      {mode === "public_fast" ? (
        <Field
          className="mt-4 lg:mt-6 lg:max-w-sm"
          label="공용 급속 단가"
          suffix="원/kWh"
          inputMode="decimal"
          value={priceInput}
          onChange={(event) => setPriceInput(event.target.value)}
          hint="공용 급속은 충전사업자마다 요금이 달라요. 충전기에 적힌 kWh당 요금을 넣어 주세요."
        />
      ) : null}

      <div className="mt-4 grid gap-4 lg:mt-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start lg:gap-6">
        {/* 차트 */}
        <Card className="p-4 lg:p-6">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-base font-bold text-ink">
              시간별 단가
              <span className="ml-2 hidden text-sm font-medium text-ink-2 lg:inline">
                원/kWh
              </span>
            </h2>
            <span className="text-sm text-ink-2 lg:hidden">원/kWh</span>
            {data ? (
              <div className="hidden lg:block">
                <BandLegend
                  keys={presentBandKeys(hours)}
                  markers={[{ label: MARKER_LABEL, tone: "ink" }]}
                />
              </div>
            ) : null}
          </div>

          {load.status === "error" ? (
            <div
              role="alert"
              className="mt-4 rounded-field bg-warn-bg px-4 py-3.5 text-sm text-warn-fg"
            >
              <p className="font-bold">단가를 불러오지 못했습니다</p>
              <p className="mt-1 whitespace-pre-line">{load.message}</p>
              <Button
                variant="outline"
                className="mt-3"
                onClick={() => setRetryCount((count) => count + 1)}
              >
                다시 시도
              </Button>
            </div>
          ) : data ? (
            <>
              <PriceBarChart
                className="mt-4 lg:mt-8"
                columns={toColumns(hours)}
                markers={[{ hours: cheapestHours(hours), tone: "ink", label: MARKER_LABEL }]}
                /* 모바일에서 24개를 다 찍으면 시각 라벨이 서로 겹친다 */
                labelEvery={isDesktop ? 1 : 6}
                plotHeight={isDesktop ? 360 : 190}
              />
              {solarOn && solarForDay ? (
                <SolarOverlay
                  className="mt-4"
                  hours={solarForDay.hours}
                  columns={hours.map((item) => item.hour)}
                  assumptions={solarForDay.assumptions}
                />
              ) : null}
              <BandLegend
                keys={presentBandKeys(hours)}
                markers={[{ label: MARKER_LABEL, tone: "ink" }]}
                className="mt-3 lg:hidden"
              />
            </>
          ) : (
            <ChartSkeleton />
          )}

          <div className="mt-6 hidden lg:block">
            <SolarOverlayButton
              on={solarOn}
              state={solarState}
              onToggle={() => setSolarOn((value) => !value)}
            />
          </div>
        </Card>

        {/* 오른쪽 사이드 (모바일에서는 차트 아래로 흐른다) */}
        <div className="grid gap-4">
          {data && hasDiscount(hours) && discountRange ? (
            <DiscountBanner range={discountRange} scope={discountScopeLabel(data)} />
          ) : null}

          {data ? (
            <PriceListCard rows={bandPriceRows(hours)} note={tariffNote} />
          ) : null}

          {/* 모바일에는 이 버튼이 없다 (디자인 p-04) — 하단 탭바의 "충전 추천"이 같은 곳으로 간다. */}
          {data && day ? (
            <div className="hidden lg:block">
              <ButtonLink
                href={recommendHref(day, mode, publicBasePrice)}
                size="lg"
                className="w-full"
              >
                이 날짜로 충전 시간 추천받기
              </ButtonLink>
            </div>
          ) : null}
        </div>

        {/* 모바일에서는 맨 아래. 데스크톱 자리는 차트 카드 안이라 여기선 숨긴다. */}
        <div className="lg:hidden">
          <SolarOverlayButton
            on={solarOn}
            state={solarState}
            onToggle={() => setSolarOn((value) => !value)}
          />
        </div>
      </div>
    </PageContainer>
  );
}

function ChartSkeleton() {
  // 24칸을 실제 막대와 같은 자리에 세워 둔다. 로딩이 끝나도 레이아웃이 튀지 않는다.
  const heights = [52, 52, 52, 52, 52, 52, 52, 52, 78, 78, 78, 40, 40, 40, 78, 78, 78, 78, 78, 78, 78, 78, 52, 52];
  return (
    <div className="mt-4 lg:mt-8" aria-hidden>
      <div className="flex h-[190px] items-end gap-[2px] lg:h-[360px]">
        {heights.map((height, index) => (
          <div
            key={index}
            className="flex-1 animate-pulse rounded-t-[3px] bg-sunken"
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
      <div className="mt-2 border-t border-line pt-3">
        <div className="h-3 w-40 animate-pulse rounded-pill bg-sunken" />
      </div>
    </div>
  );
}

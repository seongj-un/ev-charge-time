import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { RecommendResponse } from "@/lib/api/types";
import { formatHm, formatSignedWon, formatWon } from "@/lib/format";
import type { RecommendForm } from "@/lib/recommend-params";

import { planSummarySentence } from "./plan-text";

/**
 * 화면에서 제일 먼저 읽혀야 하는 네 덩어리: 추천 시각, 지금 바로의 값, 추천의 값, 그 차이.
 *
 * 모바일은 [검정][지금 바로][추천][라임 절감액] 네 장,
 * 데스크톱은 [검정][지금 바로][라임 추천] 세 장이다.
 * "추천" 카드는 모바일에서 흰 카드 + 브랜드(네이비) 테두리, 데스크톱에서 라임 카드로 바뀐다 —
 * 같은 금액을 두 번 그리지 않으려고 카드 하나에 클래스만 갈아 끼웠다.
 */
export function PlanCards({
  form,
  response,
  /** 추천 구간이 어느 부하구간에 걸쳤는지. 단가를 못 받았으면 null */
  bestBand,
  baselineBand,
}: {
  form: RecommendForm;
  response: RecommendResponse;
  bestBand: string | null;
  baselineBand: string | null;
}) {
  const { best, baseline_now, savings_won } = response;
  // 절감액이 0 이하일 수도 있다 (지금이 이미 제일 싼 때). 그때 라임 카드로 축하하면
  // 아끼지도 않은 것을 아꼈다고 말하는 셈이라, 톤과 문구를 둘 다 바꾼다.
  const saves = savings_won > 0;

  return (
    <div className="mt-5 grid grid-cols-2 gap-3 lg:mt-6 lg:grid-cols-3 lg:gap-5">
      <Card tone="ink" className="col-span-2 p-5 lg:col-span-1 lg:p-6">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-bold text-white/70">추천 충전 시간</p>
          {bestBand ? <Badge tone="ok">{bestBand}</Badge> : null}
        </div>

        <p className="mt-4 flex items-baseline gap-3 lg:mt-5 lg:gap-4">
          <span className="tnum text-[34px] font-bold leading-none lg:text-[38px]">
            {formatHm(best.start)}
          </span>
          <span className="sr-only">부터</span>
          <span className="text-2xl font-bold text-white/50" aria-hidden>
            –
          </span>
          <span className="tnum text-[34px] font-bold leading-none lg:text-[38px]">
            {formatHm(best.end)}
          </span>
          <span className="sr-only">까지</span>
        </p>

        <p className="mt-4 text-sm text-white/70">
          {planSummarySentence({
            earliestStart: form.earliestStart,
            deadline: form.deadline,
            start: best.start,
            end: best.end,
          })}
        </p>
      </Card>

      <Card className="p-4 lg:p-6">
        <p className="text-sm font-bold text-ink-2">
          지금 바로 · <span className="tnum">{formatHm(baseline_now.start)}</span>
        </p>
        <p className="tnum mt-3 text-2xl font-bold lg:mt-5 lg:text-[30px]">
          {formatWon(baseline_now.cost_won)}
        </p>
        {baselineBand ? (
          <p className="mt-3 hidden text-sm text-ink-2 lg:block">{baselineBand} 시간대</p>
        ) : null}
      </Card>

      {/*
        Card 컴포넌트를 쓰지 않은 이유: 기본 테두리(1px)와 강조 테두리(2px)가 한 요소에
        겹치면 어느 쪽이 이기는지 Tailwind가 클래스를 내보내는 순서에 달린다.
        이 카드만 테두리를 직접 쓴다.
      */}
      <div
        className={`rounded-card border-2 border-brand bg-surface p-4 lg:p-6 ${
          saves ? "lg:border-transparent lg:bg-accent" : "lg:border-line"
        }`}
      >
        <p className="text-sm font-bold text-brand lg:text-ink">
          <span className="lg:hidden">
            추천 · <span className="tnum">{formatHm(best.start)}</span>
          </span>
          <span className="hidden lg:inline">추천대로 충전하면</span>
        </p>
        <p className="tnum mt-3 text-2xl font-bold text-ink lg:mt-5 lg:text-[30px]">
          {formatWon(best.cost_won)}
        </p>
        <p className="mt-3 hidden text-sm font-bold text-ink lg:block">
          {saves ? `${formatWon(savings_won)} 절약` : "지금 시작과 요금 차이가 없어요"}
        </p>
      </div>

      {/* 절감액 강조는 모바일 전용. 데스크톱에서는 위 라임 카드가 같은 말을 한다. */}
      <Card
        tone={saves ? "accent" : "sunken"}
        className="col-span-2 flex items-center justify-between gap-3 p-4 lg:hidden"
      >
        <p className="text-sm font-bold">{saves ? "이만큼 아껴요" : "요금 차이가 없어요"}</p>
        <p className="tnum text-2xl font-bold">{formatSignedWon(savings_won)}</p>
      </Card>
    </div>
  );
}

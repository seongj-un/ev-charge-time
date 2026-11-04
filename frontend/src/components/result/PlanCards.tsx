import { Badge } from "@/components/ui/Badge";
import type { RecommendResponse } from "@/lib/api/types";
import { formatHm, formatSignedWon, formatWon } from "@/lib/format";
import type { RecommendForm } from "@/lib/recommend-params";

import { planSummarySentence } from "./plan-text";

/**
 * 화면에서 제일 먼저 읽혀야 하는 네 덩어리: 추천 시각, 지금 바로의 값, 추천의 값, 그 차이.
 *
 * 한 장의 판(panel)이다. 왼쪽(모바일은 위)에 추천 시각을 화면에서 가장 큰 글자로,
 * 오른쪽에 "지금 바로 vs 추천" 두 줄과 라임 절감액을 둔다. 예전엔 같은 무게의 카드
 * 서너 장이 나란히 있어서 무엇이 답인지 눈이 한 번 더 찾아야 했다.
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
  // 절감액이 0 이하일 수도 있다 (지금이 이미 제일 싼 때). 그때 라임으로 축하하면
  // 아끼지도 않은 것을 아꼈다고 말하는 셈이라, 톤과 문구를 둘 다 바꾼다.
  const saves = savings_won > 0;

  return (
    <section
      aria-label="추천 결과 요약"
      className="overflow-hidden rounded-panel bg-surface shadow-panel lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]"
    >
      <div className="p-5 sm:p-6 lg:p-9">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-bold text-ink-2">추천 충전 시간</p>
          {bestBand ? <Badge tone="ok">{bestBand}</Badge> : null}
        </div>

        <p className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 lg:mt-6 lg:gap-x-4">
          <span className="tnum text-figure text-ink lg:text-figure-lg">{formatHm(best.start)}</span>
          <span className="sr-only">부터</span>
          <span className="self-center text-3xl font-extrabold text-ink-2 lg:text-5xl" aria-hidden>
            –
          </span>
          <span className="tnum text-figure text-ink lg:text-figure-lg">{formatHm(best.end)}</span>
          <span className="sr-only">까지</span>
        </p>

        <p className="mt-4 text-base font-bold text-brand lg:mt-6">
          {planSummarySentence({
            earliestStart: form.earliestStart,
            deadline: form.deadline,
            start: best.start,
            end: best.end,
          })}
        </p>
      </div>

      <div className="flex flex-col border-t border-line bg-field lg:border-t-0 lg:border-l">
        <dl className="flex-1 divide-y divide-line px-5 sm:px-6 lg:px-8">
          <div className="flex items-baseline justify-between gap-3 py-4 lg:py-5">
            <dt className="text-sm font-bold text-ink-2">
              지금 바로 · <span className="tnum">{formatHm(baseline_now.start)}</span>
              {baselineBand ? <span className="mt-0.5 block font-medium">{baselineBand} 시간대</span> : null}
            </dt>
            <dd className="tnum text-xl font-extrabold text-ink-2 lg:text-2xl">{formatWon(baseline_now.cost_won)}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3 py-4 lg:py-5">
            <dt className="text-sm font-bold text-ink">
              추천대로 충전하면 · <span className="tnum">{formatHm(best.start)}</span>
            </dt>
            <dd className="tnum text-xl font-extrabold text-ink lg:text-2xl">{formatWon(best.cost_won)}</dd>
          </div>
        </dl>

        <div
          className={`flex items-center justify-between gap-3 px-5 py-5 sm:px-6 lg:px-8 lg:py-6 ${
            saves ? "bg-accent text-ink" : "bg-sunken text-ink"
          }`}
        >
          <p className="text-base font-extrabold">{saves ? "이만큼 아껴요" : "요금 차이가 없어요"}</p>
          <p className="tnum text-[32px] font-extrabold leading-none tracking-tight lg:text-[40px]">
            {formatSignedWon(savings_won)}
          </p>
        </div>
      </div>
    </section>
  );
}

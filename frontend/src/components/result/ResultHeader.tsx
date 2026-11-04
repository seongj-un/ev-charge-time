import Link from "next/link";
import type { ReactNode } from "react";

import { ChevronLeftIcon } from "@/components/shell/icons";
import { MODE_LABEL } from "@/lib/api/types";
import { requiredEnergyKwh } from "@/lib/charging";
import { formatKoreanDate, formatKwh } from "@/lib/format";
import type { RecommendForm } from "@/lib/recommend-params";

/**
 * 결과 화면 맨 윗줄.
 *
 * 모바일과 데스크톱이 같은 것들을 다르게 배치한다 (뒤로가기 + 제목 + 조건 요약 + 고지).
 * 두 벌로 나눠 그리지 않고 grid 배치만 바꾸는 이유: 조건 요약을 두 번 그리면
 * 스크린리더가 "10월 7일 (수) 자가 저압..."을 두 번 읽고, 테스트에서도 같은 글자가
 * 두 번 잡혀 무엇을 검사하는지 흐려진다.
 */
export function ResultHeader({
  form,
  query,
  unverified,
}: {
  form: RecommendForm;
  query: string;
  /** 확인 전 요금 항목이 있는지. 데스크톱은 여기 알약으로도 한 번 더 알린다. */
  unverified: boolean;
}) {
  return (
    <div
      className="grid grid-cols-[auto_1fr] items-center gap-x-2 gap-y-4
        lg:grid-cols-[auto_auto_1fr_auto] lg:gap-x-3 lg:gap-y-0"
    >
      {/* 조건을 그대로 달고 돌아간다 — 입력 화면이 방금 넣은 값을 다시 채울 수 있다. */}
      <Link
        href={`/recommend?${query}`}
        className="-ml-2 flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-lg p-1 text-on-brand-2 transition-colors duration-150
          hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent lg:ml-0 lg:min-w-0 lg:justify-start"
      >
        <ChevronLeftIcon className="size-5 lg:size-4" />
        <span className="sr-only lg:not-sr-only lg:text-sm lg:font-bold lg:underline lg:underline-offset-4">
          조건 수정
        </span>
      </Link>

      <h1 className="text-title text-white lg:text-title-lg">추천 결과</h1>

      <ConditionSummary
        form={form}
        className="col-span-2 lg:col-span-1 lg:col-start-3 lg:row-start-1 lg:justify-self-start"
      />

      {unverified ? (
        <UnverifiedPill className="hidden lg:col-start-4 lg:row-start-1 lg:inline-flex lg:justify-self-end" />
      ) : null}
    </div>
  );
}

/**
 * 조건 요약. 모바일은 알약 세 개, 데스크톱은 하나로 붙은 알약이다.
 * 같은 마크업에 클래스만 바꿔서, 두 화면이 서로 다른 값을 보여줄 여지를 없앤다.
 */
function ConditionSummary({
  form,
  className = "",
}: {
  form: RecommendForm;
  className?: string;
}) {
  // 서버 응답이 오기 전에도 보여줘야 하는 줄이라 필요 충전량은 프론트 식으로 낸다.
  // 금액은 절대 이렇게 내지 않는다 — 이건 사용자가 넣은 조건을 되읽어 주는 것뿐이다.
  const energyKwh = requiredEnergyKwh({
    batteryKwh: form.batteryKwh,
    socNow: form.socNow,
    socTarget: form.socTarget,
  });

  return (
    <div
      className={`flex flex-wrap items-center gap-2 lg:gap-0 lg:rounded-pill lg:bg-white/10 lg:px-3.5 lg:py-1.5 ${className}`}
    >
      <SummaryItem>{formatKoreanDate(form.earliestStart)}</SummaryItem>
      <SummaryDot />
      <SummaryItem>{MODE_LABEL[form.mode]}</SummaryItem>
      <SummaryDot />
      <SummaryItem>
        <span className="tnum">{formatKwh(energyKwh)}</span>
        {" · "}
        <span className="tnum">{form.chargerKw} kW</span>
      </SummaryItem>
    </div>
  );
}

function SummaryItem({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-pill bg-white/10 px-2.5 py-1 text-sm font-bold text-white lg:bg-transparent lg:px-0 lg:py-0">
      {children}
    </span>
  );
}

/** 데스크톱에서 알약 세 개가 한 줄로 붙을 때 쓰는 가운뎃점 */
function SummaryDot() {
  return (
    <span className="hidden px-1.5 text-sm font-bold text-on-brand-2 lg:inline" aria-hidden>
      ·
    </span>
  );
}

/**
 * "요금 일부 확인 중" 알약. 아래 Notice와 같은 사실을 가리키는 시각적 요약이라
 * aria-hidden으로 둔다 — 스크린리더에는 문장이 있는 Notice 쪽이 읽힌다.
 */
function UnverifiedPill({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`items-center gap-1.5 rounded-pill bg-warn-bg px-3 py-1.5 text-sm font-bold text-warn-fg ${className}`}
    >
      <svg viewBox="0 0 20 20" className="size-4 shrink-0" aria-hidden>
        <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10 9v5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="6.4" r="1" fill="currentColor" />
      </svg>
      요금 일부 확인 중
    </span>
  );
}

"use client";

import type { ReactNode } from "react";

import { ChevronLeftIcon, ChevronRightIcon } from "@/components/shell/icons";
import { formatKoreanDate } from "@/lib/format";

/**
 * ◀ 10월 10일 (토) ▶.
 *
 * 모바일은 흰 카드 한 줄을 통째로 쓰고 부제("시뮬레이션 · 봄·가을 주말")를 날짜 아래에
 * 둔다. 데스크톱은 제목 옆에 알약으로 붙고 부제는 옆의 배지로 빠진다 — 그래서 부제는
 * 여기서 lg에서 숨긴다. 같은 버튼을 두 벌 그리지 않는 게 중요하다: 화면에 안 보이는
 * "다음 날" 버튼이 하나 더 있으면 키보드 순서에 유령이 생긴다.
 *
 * day가 null인 동안(= 아직 '오늘'을 정하지 않은 첫 렌더)에는 날짜 자리만 비워 둔다.
 * 자세한 이유는 TimelineScreen 주석 참고.
 */
export function DayStepper({
  day,
  subtitle,
  onShift,
  className = "",
}: {
  day: string | null;
  subtitle?: string | null;
  onShift: (delta: number) => void;
  className?: string;
}) {
  return (
    <div
      className={`flex items-center gap-2 rounded-card border border-line bg-surface p-2 lg:gap-1 lg:rounded-pill lg:p-1.5 ${className}`}
    >
      <StepButton label="이전 날" disabled={day === null} onClick={() => onShift(-1)}>
        <ChevronLeftIcon />
      </StepButton>

      <div className="min-w-0 flex-1 px-1 text-center lg:flex-none lg:px-3">
        {day === null ? (
          <div className="mx-auto h-5 w-28 animate-pulse rounded-pill bg-sunken" aria-hidden />
        ) : (
          /* 고정폭(.tnum)은 단가·시각처럼 세로로 줄 세워 읽는 숫자용이다.
             한글이 섞인 날짜에 걸면 글자 사이가 벌어져 디자인과 어긋난다. */
          <p className="text-[15px] font-bold text-ink lg:text-base">
            {formatKoreanDate(day)}
          </p>
        )}
        {subtitle ? (
          <p className="mt-0.5 text-xs text-ink-3 lg:hidden">{subtitle}</p>
        ) : null}
      </div>

      <StepButton label="다음 날" disabled={day === null} onClick={() => onShift(1)}>
        <ChevronRightIcon />
      </StepButton>
    </div>
  );
}

function StepButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-10 shrink-0 place-items-center rounded-field bg-canvas text-ink transition-colors hover:bg-sunken active:bg-sunken disabled:opacity-45
        focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand
        lg:size-9 lg:rounded-pill"
    >
      {children}
    </button>
  );
}

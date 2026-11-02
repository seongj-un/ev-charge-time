import type { ReactNode } from "react";

/**
 * 알약 배지(상태 표시 전용). 부하구간(경부하 등)과 충전기 상태(사용 가능 등)에 같은 모양을 쓴다.
 *
 * ⚠️ `className="hidden lg:..."`로 숨으려 하면 안 숨는다 — Tailwind v4 출력에서
 * `.inline-flex`가 `.hidden`보다 뒤에 있어 이긴다. 래퍼로 감싸라:
 *     <span className="hidden lg:block"><Badge … /></span>
 * Button.tsx에 같은 설명이 더 길게 적혀 있다.
 */
type Tone = "ok" | "warn" | "off" | "ink" | "outline";

const TONE: Record<Tone, string> = {
  ok: "bg-ok-bg text-ok-fg",
  warn: "bg-warn-bg text-warn-fg",
  off: "bg-off-bg text-off-fg",
  ink: "bg-ink text-white",
  outline: "bg-transparent text-ink-2 border border-line",
};

export function Badge({
  tone = "off",
  children,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-pill px-2.5 py-1 text-sm leading-5 font-bold whitespace-nowrap ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

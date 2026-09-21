import type { ReactNode } from "react";

/**
 * 알약 배지. 부하구간(경부하 등)과 충전기 상태(사용 가능 등)에 같은 모양을 쓴다.
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
      className={`inline-flex items-center rounded-pill px-2.5 py-1 text-xs font-bold whitespace-nowrap ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

import type { ReactNode } from "react";

const InfoIcon = () => (
  <svg viewBox="0 0 20 20" className="size-4 shrink-0 mt-0.5" aria-hidden>
    <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 9v5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    <circle cx="10" cy="6.4" r="1" fill="currentColor" />
  </svg>
);

/**
 * "요금 일부 확인 중" 같은 고지.
 *
 * 이 배너를 접거나 지우지 않는 건 의도된 것이다. 백엔드가 응답마다
 * unverified_tariff_items를 실어 보내는 이유와 같다 — 금액이 잠정치라는 사실을
 * 화면에서 숨기면 심사위원에게 확정 금액처럼 보인다.
 */
export function Notice({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex gap-2 rounded-field bg-warn-bg px-3.5 py-3 text-sm text-warn-fg ${className}`}
    >
      <InfoIcon />
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

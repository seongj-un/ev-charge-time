import Link from "next/link";

import { BoltIcon } from "./icons";
import { SERVICE_NAME } from "./nav";

/**
 * 로고. 라임 정사각 칩 안의 번개 + 서비스 이름.
 * 상단 내비(데스크톱)와 모바일 상단 바가 같은 걸 쓴다 — 둘 다 네이비 면 위에 있다.
 */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`flex min-h-11 items-center gap-2.5 rounded-field text-[17px] font-extrabold tracking-tight text-white
        focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${className}`}
    >
      <span className="grid size-8 place-items-center rounded-lg bg-accent text-ink" aria-hidden>
        <BoltIcon className="size-[18px]" />
      </span>
      {SERVICE_NAME}
    </Link>
  );
}

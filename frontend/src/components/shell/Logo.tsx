import Link from "next/link";

import { BoltIcon } from "./icons";
import { SERVICE_NAME } from "./nav";

/** 로고. 메인색 정사각 칩 안의 흰 번개 + 서비스 이름. 상단 내비와 모바일 상단 바가 같이 쓴다. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`flex min-h-11 items-center gap-2 rounded-field text-[17px] font-bold tracking-tight text-ink ${className}`}
    >
      <span className="grid size-7 place-items-center rounded-lg bg-brand text-white" aria-hidden>
        <BoltIcon className="size-4" />
      </span>
      {SERVICE_NAME}
    </Link>
  );
}

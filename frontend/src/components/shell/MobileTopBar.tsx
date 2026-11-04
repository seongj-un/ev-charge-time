"use client";

import Link from "next/link";

import { useSession } from "@/components/auth/SessionProvider";

import { Logo } from "./Logo";

/**
 * 모바일 상단 바. 예전에는 화면마다 로고 줄을 직접 달았는데(홈·추천만), 그러다 보니
 * 다른 화면에는 서비스 이름이 아예 없었다. 셸이 한 번만 그린다.
 */
export function MobileTopBar() {
  const { status } = useSession();

  return (
    <header className="bg-brand-deep lg:hidden">
      <div className="flex h-14 items-center justify-between px-5 sm:px-6">
        <Logo />
        {status === "anonymous" ? (
          <Link
            href="/login"
            className="inline-flex min-h-11 items-center rounded-field px-2 text-sm font-bold text-white
              focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            로그인
          </Link>
        ) : null}
      </div>
    </header>
  );
}

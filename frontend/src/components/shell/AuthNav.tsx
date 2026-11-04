"use client";

import Link from "next/link";

import { useSession } from "@/components/auth/SessionProvider";
import { ButtonLink } from "@/components/ui/Button";

import { PersonIcon } from "./icons";

/**
 * 데스크톱 상단 내비 오른쪽. 로그인 여부에 따라 갈린다. 네이비 띠 위에 놓인다.
 *
 * 확인 중(loading)에 로그인 버튼을 먼저 그리면, 이미 로그인한 사용자에게도
 * "로그인"이 한 번 번쩍였다가 이름으로 바뀐다. 그래서 확인 중에는 자리만 잡아 둔다.
 */
export function AuthNav() {
  const { status, user } = useSession();

  if (status === "loading") {
    return <div className="h-11 w-40 animate-pulse rounded-field bg-white/10" aria-hidden />;
  }

  if (status === "authenticated" && user) {
    return (
      <Link
        href="/me"
        className="flex h-11 items-center gap-2 rounded-field border border-white/25 px-4 text-sm font-bold text-white transition-colors duration-150
          hover:border-white/60 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <PersonIcon className="size-4" />
        {user.nickname ?? user.email} 님 · 마이페이지
      </Link>
    );
  }

  return (
    <>
      <Link
        href="/login"
        className="inline-flex h-11 items-center rounded-field px-4 text-sm font-bold text-white transition-colors duration-150
          hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        로그인
      </Link>
      <ButtonLink href="/signup" variant="onBrand" className="text-sm">
        회원가입
      </ButtonLink>
    </>
  );
}

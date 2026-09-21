"use client";

import Link from "next/link";

import { useSession } from "@/components/auth/SessionProvider";
import { ButtonLink } from "@/components/ui/Button";

import { PersonIcon } from "./icons";

/**
 * 데스크톱 상단 내비 오른쪽. 로그인 여부에 따라 갈린다.
 *
 * 확인 중(loading)에 로그인 버튼을 먼저 그리면, 이미 로그인한 사용자에게도
 * "로그인"이 한 번 번쩍였다가 이름으로 바뀐다. 그래서 확인 중에는 자리만 잡아 둔다.
 */
export function AuthNav() {
  const { status, user } = useSession();

  if (status === "loading") {
    return <div className="h-11 w-40 animate-pulse rounded-pill bg-sunken" aria-hidden />;
  }

  if (status === "authenticated" && user) {
    return (
      <Link
        href="/me"
        className="flex items-center gap-2 rounded-pill bg-sunken px-4 py-2.5 text-sm font-bold text-ink transition-colors hover:bg-line"
      >
        <PersonIcon className="size-4" />
        {user.nickname ?? user.email} 님 · 마이페이지
      </Link>
    );
  }

  return (
    <>
      <ButtonLink href="/login" variant="ghost" className="text-sm">
        로그인
      </ButtonLink>
      <ButtonLink href="/signup" variant="dark" className="text-sm">
        회원가입
      </ButtonLink>
    </>
  );
}

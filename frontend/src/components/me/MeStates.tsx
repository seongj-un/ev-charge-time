import Link from "next/link";
import type { ComponentProps } from "react";

import { PageContainer } from "@/components/shell/AppShell";
import { ButtonLink } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

/**
 * 로그인 전·중·실패 상태의 화면. 두 화면(/me, /me/vehicles)이 같은 걸 쓴다.
 *
 * "확인 중"과 "손님"과 "서버에 못 닿음"을 하나로 뭉치지 않는 게 요점이다.
 * 셋을 섞으면 백엔드가 꺼졌을 때 "로그인하세요"가 뜨고, 사용자는 로그인을 시도하다
 * 원인을 영영 못 찾는다. SessionProvider가 셋을 구분해 주는 이유와 같다.
 */

/** 확인 중. 실제 화면과 같은 자리에 회색 덩어리를 세워 두어 로딩이 끝나도 튀지 않게 한다. */
export function MeSkeleton() {
  return (
    <PageContainer className="pb-10">
      <div className="lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-10" aria-hidden>
        <div className="hidden lg:block">
          <div className="h-4 w-20 animate-pulse rounded-pill bg-sunken" />
          <div className="mt-6 flex flex-col gap-2">
            {[0, 1, 2, 3].map((index) => (
              <div key={index} className="h-10 animate-pulse rounded-pill bg-sunken" />
            ))}
          </div>
        </div>
        <div>
          <div className="h-8 w-40 animate-pulse rounded-field bg-sunken" />
          <div className="mt-3 h-4 w-52 animate-pulse rounded-pill bg-sunken" />
          <div className="mt-5 grid gap-3 lg:grid-cols-3 lg:gap-5">
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-28 animate-pulse rounded-card bg-sunken" />
            ))}
          </div>
        </div>
      </div>
      <p className="sr-only">불러오는 중</p>
    </PageContainer>
  );
}

/**
 * 로그인이 필요한 화면에 손님이 들어온 경우.
 *
 * next에 지금 보려던 주소를 실어 보낸다. 로그인 뒤 홈으로 떨어뜨리면 사용자가
 * 왔던 길을 다시 찾아 들어와야 한다.
 */
export function SignInRequired({
  next,
  description,
}: {
  next: string;
  description: string;
}) {
  const query = `?next=${encodeURIComponent(next)}`;
  return (
    <PageContainer className="pb-10">
      <section className="mx-auto w-full max-w-[520px] py-8 text-center lg:py-16">
        <h1 className="text-title text-ink lg:text-title-lg">
          로그인이 필요해요
        </h1>
        <p className="mt-3 text-base leading-relaxed text-ink-2">{description}</p>

        <div className="mt-6 flex flex-col gap-2.5 lg:flex-row lg:justify-center">
          <ButtonLink href={`/login${query}`} variant="primary" size="lg">
            로그인
          </ButtonLink>
          <ButtonLink href={`/signup${query}`} variant="outline" size="lg">
            회원가입
          </ButtonLink>
        </div>

        {/* 막다른 길로 두지 않는다. 추천은 로그인 없이도 전부 쓸 수 있다. */}
        <p className="mt-8 text-sm text-ink-2">
          추천은 로그인 없이도 쓸 수 있어요.{" "}
          <Link href="/recommend" className="font-bold text-brand underline underline-offset-2">
            충전 시간 추천받기
          </Link>
        </p>
      </section>
    </PageContainer>
  );
}

/** 백엔드에 닿지 못했다. 손님과 구분해서 무엇을 해야 하는지 그대로 알려준다. */
export function ServerUnreachable({ title }: { title: string }) {
  return (
    <PageContainer className="pb-10">
      <section className="mx-auto w-full max-w-[560px] py-8 lg:py-12">
        <h1 className="text-title text-ink lg:text-title-lg">{title}</h1>
        <Notice className="mt-5">
          서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하세요.
        </Notice>
      </section>
    </PageContainer>
  );
}

/** 요청이 실패했을 때 목록 자리에 놓는 한 줄. 빈 화면으로 얼버무리지 않는다. */
export function LoadFailure({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="rounded-field bg-warn-bg px-4 py-3.5 text-sm text-warn-fg">
      <p className="whitespace-pre-line leading-relaxed">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 font-bold underline underline-offset-2"
        >
          다시 시도
        </button>
      ) : null}
    </div>
  );
}

/**
 * 빨간 글씨 행동 — 삭제·회원 탈퇴 (디자인 p-08·p-09·p-21·p-22).
 *
 * ui/Button을 쓰지 않는다. Button의 ghost·outline 변형이 이미 text-ink를 달고 있고,
 * className으로 text-danger를 더해도 둘 다 기본 유틸리티라 Tailwind 출력 순서가
 * 이긴다 — 즉 빨갛게 되지 않는다(Button.tsx 머리말의 .hidden/.inline-flex와 같은 함정).
 * !important로 억지로 이기게 하느니, 색이 다투지 않는 버튼을 따로 두는 편이 낫다.
 */
export function DangerButton({
  tone = "text",
  className = "",
  ...props
}: ComponentProps<"button"> & {
  /** text: 글씨만 빨강(p-08 회원 탈퇴) · outline: 흰 배경 + 테두리(p-09 삭제) */
  tone?: "text" | "outline";
}) {
  const TONE =
    tone === "outline"
      ? "border border-line bg-surface hover:bg-danger/5 active:bg-danger/10"
      : "hover:bg-danger/10 active:bg-danger/15";
  return (
    <button
      type="button"
      className={`inline-flex h-11 items-center justify-center rounded-field px-4 text-sm font-bold text-danger transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:pointer-events-none disabled:opacity-45 ${TONE} ${className}`}
      {...props}
    />
  );
}

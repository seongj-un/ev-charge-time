import type { ReactNode } from "react";

import { MobileTopBar } from "./MobileTopBar";
import { TabBar } from "./TabBar";
import { TopNav } from "./TopNav";

/**
 * 모바일은 상단 바 + 하단 탭바, 데스크톱은 상단 내비.
 * 본문 아래 여백은 탭바가 마지막 줄을 가리지 않게 하는 것이다.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh">
      <TopNav />
      <MobileTopBar />
      <main className="pb-[calc(6rem+env(safe-area-inset-bottom))] lg:pb-20">{children}</main>
      <TabBar />
    </div>
  );
}

/** 화면 본문의 공통 가로폭·여백. 모바일은 꽉 차고 데스크톱은 가운데로 모인다. */
export function PageContainer({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mx-auto w-full max-w-[1280px] px-5 pt-6 sm:px-6 lg:px-8 lg:pt-10 ${className}`}>
      {children}
    </div>
  );
}

/**
 * 화면 머리 — 상단 내비에 이어지는 네이비 띠. 제목·설명·조작이 여기 올라간다.
 *
 * 띠 아래쪽은 일부러 넉넉히 비운다. 본문(PageBody)이 그 자리로 올라와 겹치면서
 * "머리 위에 판이 얹힌" 모양이 된다. 평평한 크림 바탕에 카드만 늘어서던 게
 * 이전 디자인이 밋밋했던 이유라, 모든 화면이 이 구조를 공유한다.
 */
export function PageHero({
  title,
  description,
  eyebrow,
  actions,
  children,
  className = "",
}: {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  /** 제목 오른쪽(데스크톱) / 아래(모바일)에 놓이는 조작 */
  actions?: ReactNode;
  /** 제목 아래 띠 안에 더 넣을 것 (요약 칩 등) */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`bg-brand-deep text-white ${className}`}>
      <div className="mx-auto w-full max-w-[1280px] px-5 pt-6 pb-16 sm:px-6 lg:px-8 lg:pt-12 lg:pb-24">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between lg:gap-10">
          <div className="min-w-0">
            {eyebrow ? <div className="mb-3 text-sm font-bold text-accent">{eyebrow}</div> : null}
            <h1 className="text-title text-white lg:text-title-lg">{title}</h1>
            {description ? (
              <p className="mt-3 max-w-[60ch] text-base leading-relaxed text-on-brand-2">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>
        {children}
      </div>
    </section>
  );
}

/** PageHero 아래 본문. 머리 띠 위로 올라와 겹친다. */
export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`relative mx-auto -mt-10 w-full max-w-[1280px] px-5 sm:px-6 lg:-mt-14 lg:px-8 ${className}`}>
      {children}
    </div>
  );
}

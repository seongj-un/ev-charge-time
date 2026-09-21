import type { ReactNode } from "react";

import { TabBar } from "./TabBar";
import { TopNav } from "./TopNav";

/**
 * 모바일은 하단 탭바, 데스크톱은 상단 내비. 디자인이 둘을 다르게 그렸다.
 * 본문 아래 여백(pb-24)은 탭바가 마지막 줄을 가리지 않게 하는 것이다.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh">
      <TopNav />
      <main className="pb-24 lg:pb-16">{children}</main>
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
    <div className={`mx-auto w-full max-w-[1280px] px-5 pt-5 lg:px-8 lg:pt-8 ${className}`}>
      {children}
    </div>
  );
}

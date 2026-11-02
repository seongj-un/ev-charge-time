"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { PageContainer } from "@/components/shell/AppShell";

/**
 * 마이페이지 안쪽 메뉴 (디자인 p-27).
 *
 * 모바일에는 이 메뉴가 없다 — 요약 화면의 목록 링크가 같은 일을 한다(p-08).
 * 그래서 그 목록도 이 배열을 그대로 읽는다. 메뉴가 하나 늘면 두 곳이 같이 늘어야
 * 하는데, 배열이 하나면 그 실수가 아예 불가능하다.
 */
export const ME_NAV = [
  { href: "/me", label: "요약" },
  { href: "/me/vehicles", label: "내 차량" },
  { href: "/me/plans", label: "충전 기록" },
  { href: "/me/favorites", label: "즐겨찾는 충전소" },
] as const;

export function MeSidebar() {
  const pathname = usePathname();

  return (
    <nav aria-label="마이페이지 메뉴" className="hidden lg:block">
      <p className="px-4 text-sm font-bold text-ink-2">마이페이지</p>
      <ul className="mt-4 flex flex-col gap-1">
        {ME_NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`relative flex min-h-11 items-center rounded-field px-4 text-base font-bold transition-colors duration-150
                  before:absolute before:left-0 before:top-3 before:bottom-3 before:w-0.5 before:rounded-full before:content-[''] ${
                    active
                      ? "bg-surface text-brand before:bg-brand"
                      : "text-ink-2 before:bg-transparent hover:bg-surface/70 hover:text-ink"
                  }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * 마이페이지 화면의 공통 뼈대: 데스크톱은 좌측 메뉴 + 본문, 모바일은 본문만.
 *
 * 사이드바와 같은 파일에 둔 건 둘이 한 몸이기 때문이다 — 그리드 열 너비와
 * 사이드바 폭이 어긋나면 바로 눈에 띄는데, 파일이 갈라져 있으면 한쪽만 고치게 된다.
 */
export function MeLayout({ children }: { children: ReactNode }) {
  return (
    <PageContainer className="pb-10">
      <div className="lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-10">
        <MeSidebar />
        <div className="min-w-0">{children}</div>
      </div>
    </PageContainer>
  );
}

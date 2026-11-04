"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthNav } from "./AuthNav";
import { Logo } from "./Logo";
import { isActive, NAV_ITEMS } from "./nav";

/**
 * 데스크톱 상단 내비. 모바일에서는 MobileTopBar + 하단 탭바가 대신한다.
 *
 * 네이비 띠다. 바로 아래 화면 머리(PageHero)도 같은 네이비라 내비와 머리가 한 덩어리로
 * 읽힌다 — 구분선은 아주 옅게만 둔다.
 */
export function TopNav() {
  const pathname = usePathname();
  const items = NAV_ITEMS.filter((item) => !item.mobileOnly);

  return (
    <header className="sticky top-0 z-40 hidden border-b border-brand-line/60 bg-brand-deep lg:block">
      <div className="mx-auto flex h-[72px] max-w-[1280px] items-center gap-10 px-8">
        <Logo />

        <nav aria-label="주요 화면">
          <ul className="flex items-center gap-1">
            {items.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    // 활성 표시: 흰 글자 + 아래 라임 선 (하단 탭바의 라임 칩과 같은 신호)
                    className={`relative flex h-11 items-center rounded-field px-3.5 text-[15px] font-bold transition-colors duration-150
                      focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent
                      after:absolute after:inset-x-3.5 after:-bottom-[14px] after:h-[3px] after:rounded-full after:content-['']
                      ${
                        active
                          ? "text-white after:bg-accent"
                          : "text-on-brand-2 after:bg-transparent hover:bg-white/8 hover:text-white"
                      }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <AuthNav />
        </div>
      </div>
    </header>
  );
}

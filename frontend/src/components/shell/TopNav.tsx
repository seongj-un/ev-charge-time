"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthNav } from "./AuthNav";
import { Logo } from "./Logo";
import { isActive, NAV_ITEMS } from "./nav";

/** 데스크톱 상단 내비. 모바일에서는 MobileTopBar + 하단 탭바가 대신한다. */
export function TopNav() {
  const pathname = usePathname();
  const items = NAV_ITEMS.filter((item) => !item.mobileOnly);

  return (
    <header className="sticky top-0 z-40 hidden border-b border-line bg-surface lg:block">
      <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-10 px-8">
        <Logo />

        <nav aria-label="주요 화면" className="self-stretch">
          <ul className="flex h-full items-center gap-1">
            {items.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href} className="flex h-full items-center">
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    // 활성 표시: 메인색 글자 + 헤더 아래 테두리에 붙는 메인색 선 (하단 탭바와 같은 색 신호)
                    className={`relative flex h-11 items-center rounded-field px-3.5 text-[15px] font-bold transition-colors duration-150
                      after:absolute after:inset-x-3.5 after:-bottom-[11px] after:h-0.5 after:rounded-full after:content-['']
                      ${
                        active
                          ? "text-brand after:bg-brand"
                          : "text-ink-2 after:bg-transparent hover:bg-sunken/70 hover:text-ink"
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

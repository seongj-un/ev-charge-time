"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive, NAV_ITEMS } from "./nav";

/** 모바일 하단 탭바. 데스크톱에서는 상단 내비가 대신한다. */
export function TabBar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="주요 화면"
      className="lg:hidden fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="flex">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                // 활성 표시: 브랜드 글자 + 위쪽 짧은 선 (데스크톱 상단 내비와 같은 시그니처)
                className={`relative flex min-h-14 flex-col items-center justify-center gap-1 py-2 text-xs font-bold transition-colors duration-150
                  before:absolute before:left-1/2 before:top-0 before:h-0.5 before:w-8 before:-translate-x-1/2 before:rounded-full before:content-['']
                  ${active ? "text-brand before:bg-brand" : "text-ink-2 before:bg-transparent hover:text-ink"}`}
              >
                <Icon className="size-6" />
                {item.short}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

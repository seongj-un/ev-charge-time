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
                className={`flex flex-col items-center gap-1 py-2.5 text-[11px] font-bold transition-colors
                  ${active ? "text-brand" : "text-ink-3 hover:text-ink-2"}`}
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

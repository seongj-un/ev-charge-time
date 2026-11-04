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
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
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
                className={`group flex min-h-16 flex-col items-center justify-center gap-1 py-2 text-xs font-bold transition-colors duration-150
                  ${active ? "text-brand" : "text-ink-2 hover:text-ink"}`}
              >
                {/* 활성 표시: 아이콘 뒤 옅은 메인색 칩 + 메인색 아이콘·글자. 색만이 아니라 모양(칩)으로도 구분된다. */}
                <span
                  className={`grid h-8 w-12 place-items-center rounded-pill transition-colors duration-150
                    ${active ? "bg-brand-soft text-brand" : "group-hover:bg-sunken"}`}
                >
                  <Icon className="size-[22px]" />
                </span>
                {item.short}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

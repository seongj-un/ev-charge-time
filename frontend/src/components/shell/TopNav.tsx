"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthNav } from "./AuthNav";
import { BoltIcon } from "./icons";
import { isActive, NAV_ITEMS, SERVICE_NAME } from "./nav";

/** 데스크톱 상단 내비. 모바일에서는 하단 탭바가 대신한다. */
export function TopNav() {
  const pathname = usePathname();
  const items = NAV_ITEMS.filter((item) => !item.mobileOnly);

  return (
    <header className="hidden lg:block sticky top-0 z-40 border-b border-line bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex h-[74px] max-w-[1280px] items-center gap-8 px-8">
        <Link href="/" className="flex items-center gap-2 font-bold text-ink">
          <BoltIcon className="size-5 text-brand" />
          {SERVICE_NAME}
        </Link>

        <nav aria-label="주요 화면">
          <ul className="flex items-center gap-1">
            {items.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`rounded-pill px-4 py-2 text-sm font-bold transition-colors
                      ${active ? "bg-sunken text-ink" : "text-ink-2 hover:text-ink"}`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <AuthNav />
        </div>
      </div>
    </header>
  );
}

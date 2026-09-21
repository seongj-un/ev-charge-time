import type { ComponentType } from "react";

import { BoltIcon, ChartIcon, ChatIcon, HomeIcon, PersonIcon, PinIcon } from "./icons";

/**
 * 이름이 아직 정해지지 않았다 (노션 문서 제목도 "(가칭)"). 디자인의 자리표시자를
 * 그대로 두되 한 곳에만 둔다 — 이름이 정해지면 이 상수만 고치면 된다.
 */
export const SERVICE_NAME = "[서비스명]";

export type NavItem = {
  href: string;
  label: string;
  /** 모바일 탭바에 쓰는 짧은 이름 */
  short: string;
  icon: ComponentType<{ className?: string }>;
  /** 데스크톱 상단 내비에는 띄우지 않는다 */
  mobileOnly?: boolean;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "홈", short: "홈", icon: HomeIcon, mobileOnly: true },
  { href: "/recommend", label: "충전 시간 추천", short: "충전 추천", icon: BoltIcon },
  // 조건 입력과 같은 일을 하는 다른 입구라 추천 바로 옆에 둔다.
  { href: "/ask", label: "질문하기", short: "질문", icon: ChatIcon },
  { href: "/timeline", label: "하루 단가", short: "단가", icon: ChartIcon },
  { href: "/stations", label: "주변 충전소", short: "충전소", icon: PinIcon },
  { href: "/me", label: "내 정보", short: "내 정보", icon: PersonIcon, mobileOnly: true },
];

/** 현재 경로가 어느 탭에 속하는지. /recommend/result도 /recommend 탭이다. */
export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

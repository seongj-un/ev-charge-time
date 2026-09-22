import type { ComponentType } from "react";

import { BoltIcon, ChartIcon, ChatIcon, HomeIcon, PersonIcon, PinIcon } from "./icons";

/**
 * 서비스 이름.
 *
 * 상단 내비·홈·추천 화면·브라우저 탭 제목·PWA 매니페스트가 전부 이걸 읽는다.
 * 한 곳에만 둔 덕에 이름이 정해졌을 때 이 줄만 고치면 됐다.
 */
export const SERVICE_NAME = "키네틱";

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

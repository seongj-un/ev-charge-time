import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/**
 * 디자인에 버튼이 네 종류 있다.
 *   primary  진한 네이비(브랜드) — 화면마다 하나뿐인 주 행동 ("최적 시간 찾기")
 *   dark     검정 — 인증 화면의 주 행동 ("로그인", "가입하기")
 *   outline  흰 배경 + 테두리 — 나란히 놓인 보조 행동 ("하루 단가 보기")
 *   ghost    배경 없음 — 링크에 가까운 것
 */
type Variant = "primary" | "dark" | "outline" | "ghost";
type Size = "md" | "lg";

const VARIANT: Record<Variant, string> = {
  // 호버는 팔레트 안의 더 어두운 면(ink)으로 — DESIGN.md button-primary-hover.
  primary: "bg-brand text-white not-disabled:hover:bg-ink not-disabled:active:bg-ink/90",
  dark: "bg-ink text-white not-disabled:hover:bg-ink/90 not-disabled:active:bg-ink/80",
  outline:
    "bg-surface text-ink border border-line not-disabled:hover:border-ink-3 not-disabled:hover:bg-canvas not-disabled:active:bg-sunken",
  ghost: "text-ink not-disabled:hover:bg-sunken/60 not-disabled:active:bg-sunken",
};

const SIZE: Record<Size, string> = {
  // md는 44px(터치 최소), lg는 필드와 같은 48px — 폼 제출·화면의 주 행동.
  md: "h-11 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

/*
 * ⚠️ 이 버튼을 `className="hidden lg:..."`로 숨기려 하면 안 숨겨진다.
 *
 * Tailwind v4가 내보내는 CSS에서 `.hidden`이 `.inline-flex`보다 앞에 나온다.
 * 특정도가 같으니 뒤에 있는 `.inline-flex`가 이긴다. class 속성의 순서는
 * 아무 상관이 없다 — 출력 CSS의 순서가 정한다.
 *
 * 숨기려면 표시 속성을 다투지 않는 래퍼로 감싼다:
 *     <div className="hidden lg:block"><ButtonLink … /></div>
 *
 * 반대 방향(`lg:hidden`)은 변형이 뒤에 나오므로 그냥 동작한다.
 * Badge도 같은 이유로 같은 함정이 있다.
 */
const BASE =
  "inline-flex items-center justify-center gap-2 rounded-field font-bold transition-colors duration-150 " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand " +
  "disabled:opacity-45 disabled:cursor-not-allowed";

export function buttonClass(variant: Variant = "primary", size: Size = "md") {
  return `${BASE} ${VARIANT[variant]} ${SIZE[size]}`;
}

type ButtonProps = ComponentProps<"button"> & {
  variant?: Variant;
  size?: Size;
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonProps) {
  return <button className={`${buttonClass(variant, size)} ${className}`} {...props} />;
}

type ButtonLinkProps = ComponentProps<typeof Link> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
};

export function ButtonLink({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonLinkProps) {
  return <Link className={`${buttonClass(variant, size)} ${className}`} {...props} />;
}

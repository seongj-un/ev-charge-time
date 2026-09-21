import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

/**
 * 디자인에 버튼이 네 종류 있다.
 *   primary  진한 초록 — 화면마다 하나뿐인 주 행동 ("최적 시간 찾기")
 *   dark     검정 — 인증 화면의 주 행동 ("로그인", "가입하기")
 *   outline  흰 배경 + 테두리 — 나란히 놓인 보조 행동 ("하루 단가 보기")
 *   ghost    배경 없음 — 링크에 가까운 것
 */
type Variant = "primary" | "dark" | "outline" | "ghost";
type Size = "md" | "lg";

const VARIANT: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand/90 active:bg-brand/80",
  dark: "bg-ink text-white hover:bg-ink/90 active:bg-ink/80",
  outline:
    "bg-surface text-ink border border-line hover:bg-canvas active:bg-sunken",
  ghost: "text-ink hover:bg-sunken/60",
};

const SIZE: Record<Size, string> = {
  md: "h-11 px-4 text-sm",
  lg: "h-14 px-6 text-base",
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-pill font-bold transition-colors " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand " +
  "disabled:opacity-45 disabled:pointer-events-none";

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

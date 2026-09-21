import type { ComponentProps } from "react";

/**
 * 디자인의 카드는 세 가지 톤을 쓴다.
 *   surface  흰 카드 — 기본
 *   ink      검정 카드 — 추천 시각처럼 화면에서 제일 먼저 읽혀야 하는 것
 *   accent   라임 카드 — 절감액
 */
type Tone = "surface" | "ink" | "accent" | "sunken";

const TONE: Record<Tone, string> = {
  surface: "bg-surface border border-line text-ink",
  ink: "bg-ink text-white",
  accent: "bg-accent text-ink",
  sunken: "bg-sunken text-ink",
};

type CardProps = ComponentProps<"div"> & {
  tone?: Tone;
};

export function Card({ tone = "surface", className = "", ...props }: CardProps) {
  return (
    <div
      className={`rounded-card ${TONE[tone]} ${className}`}
      {...props}
    />
  );
}

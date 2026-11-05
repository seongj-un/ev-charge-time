import type { Band, Mode } from "@/lib/api/types";

/**
 * 부하구간 → 색. 차트 막대와 범례가 같은 곳에서 색을 가져와야
 * "범례는 초록인데 막대는 왜 다른 초록이지"가 생기지 않는다.
 *
 * 주말 할인은 부하구간이 아니라 그 위에 얹히는 상태다. 할인이 걸린 시각은
 * 원래 구간이 무엇이든 라임으로 칠한다 — 디자인이 그렇게 구분했다.
 */
export type BandKey = Band | "discounted" | "flat";

export const BAND_COLOR: Record<BandKey, string> = {
  light: "var(--color-band-light)",
  middle: "var(--color-band-middle)",
  peak: "var(--color-band-peak)",
  discounted: "var(--color-accent)",
  flat: "var(--color-ink-2)",
};

export const BAND_KEY_LABEL: Record<BandKey, string> = {
  light: "경부하",
  middle: "중간",
  peak: "최대",
  discounted: "주말 할인",
  flat: "기본 단가",
};

/** 범례에 쓸 긴 이름 (단가 목록에서는 "중간" 대신 "중간부하") */
export const BAND_KEY_LONG_LABEL: Record<BandKey, string> = {
  light: "경부하",
  middle: "중간부하",
  peak: "최대부하",
  discounted: "주말 할인",
  flat: "기본 단가",
};

/**
 * 공공 급속은 시간대와 상관없이 단가가 하나다(주말 할인 시각만 다르다). 백엔드는 공공
 * 급속에도 부하구간 이름을 붙여 보내지만, 그대로 칠하면 값이 같은 막대가 "최대부하"
 * 빨강으로 보여 비싼 시간처럼 읽힌다. 그래서 할인 아닌 시각은 "기본 단가" 하나로 묶는다.
 */
export function bandKeyOf(band: Band, discounted: boolean, mode?: Mode): BandKey {
  if (discounted) return "discounted";
  return mode === "public_fast" ? "flat" : band;
}

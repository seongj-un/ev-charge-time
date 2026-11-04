import type { CSSProperties } from "react";

/**
 * 등장 애니메이션(.motion-rise · .motion-grow · .motion-pop)의 시작 지연.
 * 여러 개가 차례로 나타나게 할 때 쓴다. 값은 globals.css의 --motion-delay로 들어간다.
 * 움직임 줄이기 설정에서는 globals.css가 지연과 길이를 모두 0으로 만든다.
 */
export function motionDelay(ms: number): CSSProperties {
  return { "--motion-delay": `${Math.round(ms)}ms` } as CSSProperties;
}

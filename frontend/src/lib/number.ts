/**
 * 입력 칸의 숫자. 사람이 치는 꼴만 받는다: "70", "70.5", ".5", "-5".
 *
 * 빈 칸을 0으로 읽지 않으려고 Number()를 그냥 쓰지 않고, "1e3"·"0x10"·"Infinity"처럼
 * Number()가 받아 주는 표기도 막는다 — "1e3"을 1000으로 읽으면 화면의 값과 계산한
 * 값이 달라진다. 범위(0보다 큼 등)는 부르는 쪽이 칸마다 따로 본다.
 */
export function parseDecimal(raw: string): number | null {
  const text = raw.trim();
  if (!/^-?(\d+(\.\d*)?|\.\d+)$/.test(text)) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/** 백엔드 schemas.MAX_BATTERY_KWH / MAX_CHARGER_KW와 같다. 넘기면 서버가 422로 거절한다. */
export const MAX_BATTERY_KWH = 1000;
export const MAX_CHARGER_KW = 1000;

import { MODE_LABEL, type Vehicle } from "@/lib/api/types";
import { formatKwh } from "@/lib/format";

/**
 * 마이페이지에서만 쓰는 문자열 만들기.
 *
 * lib/format.ts에 넣지 않은 이유: 차량 사양 한 줄은 이 화면들의 표현이지 서비스
 * 공통 규칙이 아니다. 나중에 다른 화면이 같은 줄을 쓰게 되면 그때 올린다.
 */

/** "7 kW" · "3.5 kW" — 소수점이 필요 없으면 붙이지 않는다. */
export function formatKw(kw: number): string {
  return `${Math.round(kw * 10) / 10} kW`;
}

/** "70 kWh · 7 kW · 자가 저압" (디자인 p-08·p-09) */
export function vehicleSpecLine(vehicle: Vehicle): string {
  return `${formatKwh(vehicle.battery_kwh)} · ${formatKw(vehicle.charger_kw)} · ${MODE_LABEL[vehicle.mode]}`;
}

/**
 * 지금이 몇 월인지 — KST 기준 "YYYY-MM".
 *
 * 브라우저 표준시로 계산하면 해외에 있는 심사위원의 노트북에서 달이 하나 어긋난다.
 * 백엔드가 KST로 집계하므로 프론트도 KST로 물어야 같은 달을 본다.
 * (en-CA 로캘이 ISO와 같은 "2026-09" 모양을 준다.)
 */
export function currentMonthInSeoul(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
  }).format(now);
}

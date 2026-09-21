import { BAND_COLOR, BAND_KEY_LONG_LABEL } from "@/components/chart/bands";
import { Card } from "@/components/ui/Card";

import { formatBandPrice, type BandPriceRow } from "./timeline-view";

/**
 * 부하구간별 단가 목록. 차트가 색으로 말하는 것을 글자로 한 번 더 말한다 —
 * 중간부하와 주말 할인은 흰 배경 대비가 3:1 아래라 색만으로는 못 읽는 사람이 있다.
 *
 * rows에는 오늘 실제로 나타난 구간만 들어온다. 최대부하가 없는 날에 "최대부하 —"를
 * 한 줄 비워 두면, 없는 걸 보여주는 것보다 있는 걸 못 찾게 만드는 쪽이 더 나쁘다.
 */
export function PriceListCard({
  rows,
  className = "",
}: {
  rows: BandPriceRow[];
  className?: string;
}) {
  return (
    <Card className={`overflow-hidden ${className}`}>
      <ul aria-label="부하구간별 단가">
        {rows.map((row) => (
          <li
            key={row.key}
            className="flex items-center gap-2.5 border-b border-line px-4 py-3.5 last:border-b-0 lg:px-5"
          >
            <span
              className="size-2.5 shrink-0 rounded-[3px]"
              style={{ background: BAND_COLOR[row.key] }}
              aria-hidden
            />
            <span className="flex-1 text-[15px] font-bold text-ink">
              {BAND_KEY_LONG_LABEL[row.key]}
            </span>
            <span className="tnum text-lg font-bold text-ink">{formatBandPrice(row)}</span>
          </li>
        ))}
      </ul>

      {/*
       * 늘 붙어 있어야 하는 줄이다. 2026년 개편 요금표가 아직 공식 확인 전이라
       * 여기 숫자는 전부 잠정치다 — 각주를 빼면 화면이 확정 요금을 말하는 게 된다.
       */}
      <p className="border-t border-line px-4 py-3 text-xs text-ink-3 lg:px-5">
        <span className="hidden lg:inline">원/kWh · </span>
        예시 값 · 요금표 확정 후 바뀝니다
      </p>
    </Card>
  );
}

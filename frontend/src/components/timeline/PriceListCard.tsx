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
  note,
  className = "",
}: {
  rows: BandPriceRow[];
  /** 요금이 얼마나 확인됐는지. 확인이 끝났으면 null. */
  note: string | null;
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
       * 각주를 고정 문장으로 두면 요금표가 바뀔 때 조용히 틀린다 — 실제로 그랬다.
       * "예시 값 · 요금표 확정 후"라고 적어 뒀는데 한전 공식 요금표가 들어오면서
       * 이 단가들은 확정됐고 각주만 남아 거짓말이 됐다. 이제 서버가 알려주는
       * 미확인 항목에서 문장을 만들고, 남은 게 없으면 출처만 적는다.
       */}
      <p className="border-t border-line px-4 py-3 text-xs leading-relaxed text-ink-3 lg:px-5">
        <span className="hidden lg:inline">원/kWh · </span>
        {note ?? "출처: 한국전력공사 전기요금표"}
      </p>
    </Card>
  );
}

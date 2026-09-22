import type { SolarHour } from "@/lib/api/types";

/**
 * 단가 차트 위에 겹치는 태양광 발전 예측.
 *
 * **단가와 일사량을 같은 y축에 올리지 않는다.** 원/kWh와 W/m²는 단위가 달라서
 * 한 축에 올리면 이중축 차트가 되는데, 그러면 두 계열의 상대 높이를 눈금 선택으로
 * 마음대로 바꿀 수 있다 — "낮에 충전하세요"를 주장하는 화면에서 그건 과장 도구가 된다.
 *
 * 백엔드가 `output_index`를 0~1로 정규화해 보내는 이유가 이것이고, 그래서 이
 * 오버레이는 자기 높이 안에서만 그려진다. 막대와 축을 공유하지 않는다.
 */

type Props = {
  hours: SolarHour[];
  /** 차트가 실제로 그리는 시각들. 이 안에 없는 예측은 버린다. */
  columns: number[];
  assumptions: string[];
  className?: string;
};

export function SolarOverlay({ hours, columns, assumptions, className = "" }: Props) {
  const byHour = new Map(hours.map((item) => [item.hour, item]));

  return (
    <div className={className}>
      <div className="flex items-end gap-[2px]" style={{ height: 56 }} aria-hidden>
        {columns.map((hour, index) => {
          const found = byHour.get(hour);
          if (!found) {
            // 예측이 없는 시각을 0으로 그리면 "그때는 해가 없다"는 거짓이 된다.
            return <div key={index} className="flex-1" />;
          }
          return (
            <div key={index} className="flex h-full flex-1 items-end">
              <div
                data-solar-point
                className="w-full rounded-t-[3px] bg-accent/70"
                style={{ height: `${round1(found.output_index * 100)}%` }}
              />
            </div>
          );
        })}
      </div>

      {/* 색과 높이만으로 정보를 주지 않는다 — 차트 전체에 적용한 원칙이다. */}
      <table className="sr-only">
        <caption>시간별 태양광 발전 지수 (0~1)</caption>
        <tbody>
          {columns.map((hour, index) => {
            const found = byHour.get(hour);
            return (
              <tr key={index}>
                <th scope="row">{hour}시</th>
                <td
                  role="img"
                  aria-label={
                    found
                      ? `${hour}시 태양광 발전 지수 ${Math.round(found.output_index * 100)}%`
                      : `${hour}시 태양광 예측 없음`
                  }
                >
                  {found ? `${Math.round(found.output_index * 100)}%` : "예측 없음"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {assumptions.length > 0 ? (
        /*
         * "전남 전체를 5km 격자 한 칸으로 대신함" 같은 한계는 사용자가 절대
         * 짐작할 수 없다. 안 보여주면 정밀한 지역 예측이라고 읽는다 —
         * unverified_tariff_items와 같은 성격이라 같은 방식으로 다룬다.
         */
        <ul role="note" className="mt-2 flex flex-col gap-0.5 text-xs leading-relaxed text-ink-3">
          {assumptions.map((line) => (
            <li key={line}>· {line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

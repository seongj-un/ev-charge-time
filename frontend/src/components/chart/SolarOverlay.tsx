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

/** 이보다 낮으면 막대가 1~2px 선으로만 보인다. 그런 칸만 있으면 막대 대신 말로 한다. */
const DARK_INDEX = 0.03;

export function SolarOverlay({ hours, columns, assumptions, className = "" }: Props) {
  const byHour = new Map(hours.map((item) => [item.hour, item]));
  const shown = columns.map((hour) => byHour.get(hour)).filter((item) => item !== undefined);
  /*
   * 밤 시간대 축(17시→다음날 7시)이면 막대가 전부 0이라 56px 빈 칸만 남는다.
   * 사용자는 그걸 "고장"으로 읽었다. 해가 없다는 걸 말로 적는다.
   */
  const dark = shown.length > 0 && shown.every((item) => item.output_index < DARK_INDEX);
  // 막대를 그리지 않을 때는 막대를 설명하는 줄도 뺀다.
  const notes = plainSolarNotes(assumptions).filter((line) => !dark || !line.includes("막대"));

  return (
    <div className={className}>
      {dark ? (
        <p className="text-sm text-ink-2">
          이 시간대는 해가 없거나 낮아서 태양광 발전이 거의 없어요.
        </p>
      ) : (
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
      )}

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

      {notes.length > 0 ? (
        /*
         * "전남 전체를 한 지점 예보로 대신함" 같은 한계는 사용자가 짐작할 수 없어 꼭 보인다.
         * 다만 서버가 주는 문장은 개발용 말(nx=57, predicted_mwh, 20261110 1400)이 섞여 있어
         * 사람 말로 옮겨 보이고, 원문은 접어 둔다 — "근거가 뭐냐"는 질문에 답할 수 있게.
         */
        <div role="note" className="mt-2 text-sm leading-relaxed text-ink-2">
          <ul className="flex flex-col gap-0.5">
            {notes.map((line) => (
              <li key={line}>· {line}</li>
            ))}
          </ul>
          <details className="mt-1">
            <summary className="cursor-pointer">예보 근거 원문</summary>
            <ul className="mt-1 flex flex-col gap-0.5">
              {assumptions.map((line) => (
                <li key={line}>· {line}</li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}
    </div>
  );
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * 서버가 준 예보 전제를 사람 말로 옮긴다. 모르는 줄은 개발용 낱말이 없을 때만 그대로 둔다.
 * 빈 배열이면 빈 배열 — 전제가 없는데 설명 상자를 만들지 않는다.
 */
export function plainSolarNotes(assumptions: string[]): string[] {
  if (assumptions.length === 0) return [];
  const notes = ["막대 높이는 햇빛 세기예요. 맑은 날 한낮 최대를 100%로 봤어요."];
  for (const line of assumptions) {
    const issued = /단기예보 (\d{4})(\d{2})(\d{2}) (\d{2})(\d{2}) 발표/.exec(line);
    let plain: string | null;
    if (/격자/.test(line)) {
      plain = "전남 전체를 한 지점의 기상청 예보로 대신한 참고값이에요.";
    } else if (issued) {
      const [, , month, day, hour] = issued;
      plain = `기상청 ${Number(month)}월 ${Number(day)}일 ${Number(hour)}시 발표 예보를 썼어요.`;
    } else if (/일부 시간대만|예보가 아직 없는/.test(line)) {
      plain = "예보가 아직 없는 시간은 막대를 비워 두었어요.";
    } else if (/설비용량/.test(line)) {
      plain = null; // 화면은 발전량(MWh)을 쓰지 않는다. 사용자에게 의미 없는 줄이다.
    } else {
      plain = /[A-Za-z]+_[A-Za-z]|nx=|\d{8}/.test(line) ? null : line;
    }
    if (plain && !notes.includes(plain)) notes.push(plain);
  }
  return notes;
}

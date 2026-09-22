/**
 * 요금이 얼마나 확인됐는지를 화면 문장으로 만드는 곳.
 *
 * 결과 화면과 하루 단가 화면이 같은 사실을 말해야 해서 공용으로 둔다.
 * 한쪽만 고치면 같은 화면에서 "확정됐다"와 "잠정치다"가 동시에 보인다.
 */

/**
 * 확인 전 요금 고지 문구.
 *
 * 백엔드가 주는 unverified_tariff_items는 `public_fast.base_price_per_kwh`처럼
 * 코드 안에서 쓰는 키다. 그대로 문장에 이어 붙이면 아무도 읽지 않고, 안 읽히는
 * 고지는 고지가 아니다. 그렇다고 문장을 고정하면 요금표가 바뀔 때 조용히 틀린다 —
 * 실제로 그랬다. "시간대 구분과 부가 요금은 확인 전"이라고 적어 뒀는데 한전 공식
 * 요금표가 들어오면서 둘 다 확정됐고, 문장만 남아 거짓말이 됐다.
 *
 * 그래서 남은 항목에서 문장을 만든다. 모르는 키는 "일부 요금 항목"으로 뭉뚱그린다 —
 * 백엔드가 새 키를 추가해도 빈 문장이 나오지 않는다.
 */
const UNVERIFIED_LABEL: Record<string, string> = {
  time_bands: "시간대 구분",
  "energy_charge.self_low": "자가 저압 단가",
  "energy_charge.self_high": "자가 고압 단가",
  "public_fast.base_price_per_kwh": "공공 급속 단가",
  "public_fast.weekend_discount": "주말 할인",
  weekend_discount_self: "주말 할인",
  /*
   * 할인 자체와 적용 기한은 근거가 다르다. 봄·가을 주말 11~14시 50%는 기후에너지
   * 환경부 보도자료(2026-04-14)로 확인됐지만, "2030년까지"는 어느 공식 문서에도
   * 없어 따로 떨어져 나왔다. 둘을 같은 이름으로 부르면 확인된 할인까지 잠정치로
   * 읽힌다.
   */
  weekend_discount_sunset: "주말 할인 적용 기한",
  power_fund_rate: "전력산업기반기금",
  "adders.climate_env_per_kwh": "기후환경요금",
  "adders.fuel_adjustment_per_kwh": "연료비조정요금",
};

const UNKNOWN_LABEL = "일부 요금 항목";

/**
 * 한글 조사는 앞 글자 받침에 따라 갈린다.
 *
 * 하나로 고정하면 "단가은", "구분와" 같은 문장이 사용자에게 그대로 보인다.
 * 요금이 잠정치라는 걸 알리는 문장이 깨진 한국어면 그 고지 자체가 가벼워 보인다.
 */
function hasFinalConsonant(word: string): boolean {
  const last = word.trim().at(-1);
  if (last === undefined) return false;
  const code = last.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return false; // 한글 음절이 아니면 판단하지 않는다
  return (code - 0xac00) % 28 !== 0;
}

function withParticle(word: string, withFinal: string, withoutFinal: string): string {
  return word + (hasFinalConsonant(word) ? withFinal : withoutFinal);
}

export function unverifiedNotice(items: string[]): string | null {
  if (items.length === 0) return null;

  const labels: string[] = [];
  for (const item of items) {
    const label = UNVERIFIED_LABEL[item] ?? UNKNOWN_LABEL;
    // 같은 뜻의 키가 둘 이상 올 수 있다 (자가·공공 주말 할인). 한 번만 말한다.
    if (!labels.includes(label)) labels.push(label);
  }

  const last = labels[labels.length - 1];
  const joined =
    labels.length === 1
      ? last
      : `${labels
          .slice(0, -1)
          .map((label) => withParticle(label, "과", "와"))
          .join(" ")} ${last}`;

  return `${withParticle(joined, "은", "는")} 공식 요금표 확인 전 값입니다.`;
}

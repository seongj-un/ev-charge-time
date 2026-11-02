import { SunIcon } from "@/components/shell/icons";
import { Card } from "@/components/ui/Card";

/**
 * "11–14시 전력량요금 50% 할인 · 봄·가을 토·일·공휴일".
 *
 * 부르는 쪽 책임이 하나 있다: 이 배너는 응답의 hours에 discounted === true인 시각이
 * 실제로 있을 때만 그려야 한다. 할인 없는 날에 띄우면 그냥 거짓말이고, 사용자는
 * 있지도 않은 싼 시간대를 찾다가 화면을 못 믿게 된다. 그래서 range는 null을 받지 않는다 —
 * 할인 구간 없이는 이 컴포넌트를 만들 수조차 없게 해 두는 게 조건문보다 튼튼하다.
 *
 * 50%는 응답에 없다. 요금제 규칙에 적힌 고정 값이라 여기 상수로 둔다 —
 * 요율이 바뀌면 백엔드가 아니라 이 줄을 고쳐야 한다.
 */
const DISCOUNT_RATE_LABEL = "전력량요금 50% 할인";

export function DiscountBanner({
  range,
  scope,
  className = "",
}: {
  /** "11–14시" — 실제로 할인이 걸린 시각들에서 만든 구간 */
  range: string;
  /** "봄·가을 토·일·공휴일" — 할인이 적용되는 날 */
  scope: string;
  className?: string;
}) {
  return (
    <Card
      tone="accent"
      role="note"
      aria-label="전력량요금 할인"
      className={`px-4 py-3.5 lg:px-5 lg:py-4 ${className}`}
    >
      <div className="flex items-start gap-2.5">
        <SunIcon className="size-5 shrink-0 lg:hidden" />
        <div className="min-w-0">
          <p className="text-sm leading-snug font-bold lg:text-base">
            {range} {DISCOUNT_RATE_LABEL}
            {/* 모바일은 한 줄로 붙이고, 데스크톱은 아래 문장으로 푼다 (디자인 p-04 / p-17) */}
            <span className="text-sm font-medium lg:hidden"> · {scope}</span>
          </p>
          <p className="mt-1.5 hidden text-sm lg:block">{scope}에 적용돼요.</p>
        </div>
      </div>
    </Card>
  );
}

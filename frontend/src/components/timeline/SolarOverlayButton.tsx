"use client";

/**
 * "태양광 발전 예측 겹쳐 보기" 토글.
 *
 * 켤 수 없는 상태(백엔드 미설정 등)를 눌러서 오류로 알려주지 않는다. disabled로
 * 두고 왜 못 켜는지를 버튼 안에 적는다 — 점선 테두리도 같은 말을 하는 장치다.
 * 이름 안에 상태가 들어가야 스크린리더도 "왜 안 눌리지"를 겪지 않는다.
 *
 * 불러오다 실패한 경우("failed")는 다르다. 예보 범위 밖의 날짜나 일시적인 오류라
 * 다시 누르면 될 수도 있다. 그래서 누를 수 있게 두되, 켜진 척하지 않도록
 * "불러오지 못함"을 적고 aria-pressed도 false로 둔다.
 *
 * 모바일은 목록 맨 아래 가로 꽉 찬 줄, 데스크톱은 차트 카드 좌하단 알약이라
 * 두 자리에 각각 놓인다. 보이지 않는 쪽은 display:none이라 접근성 트리에서도 빠진다.
 */
export function SolarOverlayButton({
  on,
  onToggle,
  state,
  className = "",
}: {
  on: boolean;
  onToggle: () => void;
  /**
   * "loading"·"unavailable"은 누를 수 없고, 그 이유가 버튼에 적힌다.
   * "failed"는 이번 시도가 실패했다는 뜻이라 다시 누를 수 있다.
   */
  state: "ready" | "loading" | "unavailable" | "failed";
  className?: string;
}) {
  const note =
    state === "loading"
      ? "불러오는 중"
      : state === "unavailable"
        ? "준비 중"
        : state === "failed"
          ? "불러오지 못함"
          : on
            ? "켜짐"
            : "꺼짐";
  const disabled = state === "loading" || state === "unavailable";

  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={disabled ? undefined : state === "ready" && on}
      onClick={onToggle}
      className={`flex w-full items-center justify-between gap-2 rounded-field border border-dashed border-line
        px-4 py-3.5 text-sm text-ink-2 transition-colors disabled:opacity-100
        enabled:hover:bg-canvas enabled:border-solid
        ${on ? "bg-accent/20" : ""}
        lg:min-h-11 lg:w-auto lg:justify-start lg:rounded-field lg:px-4 lg:py-2.5 lg:text-sm ${className}`}
    >
      <span className="font-bold">태양광 발전 예측 겹쳐 보기</span>
      <span className="text-ink-2">
        <span className="hidden lg:inline">· </span>
        {note}
      </span>
    </button>
  );
}

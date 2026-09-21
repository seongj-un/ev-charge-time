/**
 * "태양광 발전 예측 겹쳐 보기 · 준비 중".
 *
 * 백엔드가 아직 501을 준다. 눌러서 오류를 보여주는 대신 disabled로 두고 "준비 중"을
 * 버튼 안에 적는다 — 점선 테두리도 같은 말을 하는 장치다. 이름 안에 상태가 들어가야
 * 스크린리더도 "왜 안 눌리지"를 겪지 않는다.
 *
 * 모바일은 목록 맨 아래 가로 꽉 찬 줄, 데스크톱은 차트 카드 좌하단 알약이라
 * 두 자리에 각각 놓인다. 보이지 않는 쪽은 display:none이라 접근성 트리에서도 빠진다.
 */
export function SolarOverlayButton({ className = "" }: { className?: string }) {
  return (
    <button
      type="button"
      disabled
      className={`flex w-full items-center justify-between gap-2 rounded-field border border-dashed border-line
        px-4 py-3.5 text-sm text-ink-2 disabled:opacity-100
        lg:w-auto lg:justify-start lg:rounded-pill lg:px-4 lg:py-2.5 lg:text-[13px] ${className}`}
    >
      <span className="font-bold">태양광 발전 예측 겹쳐 보기</span>
      <span className="text-ink-3">
        <span className="hidden lg:inline">· </span>준비 중
      </span>
    </button>
  );
}

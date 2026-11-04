import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

/**
 * 결과 화면이 결과를 못 보여주는 세 경우: 조건 없음 / 기다리는 중 / 오류.
 * 셋 다 "지금 무슨 일이고 다음에 뭘 하면 되는지"를 한 화면에 담는다.
 */

/**
 * 조건 없이 /recommend/result로 바로 들어온 경우.
 * 즐겨찾기나 공유 링크에서 쿼리가 잘려 나가면 흔히 생긴다.
 */
export function NoConditionState() {
  return (
    <Card className="mt-6 p-6 text-center lg:mt-10 lg:p-10">
      <h1 className="text-section">충전 조건이 없어요</h1>
      <p className="mx-auto mt-2 max-w-[28rem] text-sm leading-relaxed text-ink-2">
        주소에 충전 조건이 들어 있지 않아 추천을 계산할 수 없습니다. 배터리 용량과 충전
        가능한 시간을 넣으면 가장 싼 시간을 찾아드려요.
      </p>
      <ButtonLink href="/recommend" size="lg" className="mt-6">
        충전 조건 입력하기
      </ButtonLink>
    </Card>
  );
}

/** 추천을 기다리는 동안. 판 자리를 미리 잡아 두면 값이 들어올 때 화면이 튀지 않는다. */
export function ResultSkeleton() {
  return (
    <div role="status" aria-live="polite">
      <div className="overflow-hidden rounded-panel border border-line bg-surface shadow-panel lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="p-5 sm:p-6 lg:p-9">
          <p className="text-sm font-bold text-ink-2">추천을 계산하고 있어요…</p>
          <div className="mt-4 h-11 w-64 animate-pulse rounded-lg bg-sunken lg:mt-6 lg:h-16 lg:w-96" />
          <div className="mt-4 h-6 w-56 animate-pulse rounded-lg bg-sunken lg:mt-6" />
        </div>
        <div className="h-[196px] animate-pulse bg-sunken/70 lg:h-auto" />
      </div>

      <div className="mt-4 h-[260px] animate-pulse rounded-card bg-sunken lg:mt-6 lg:h-[330px]" />
    </div>
  );
}

/**
 * 오류. 백엔드가 준 문장을 그대로 보여준다 — 422의 detail은 "시간이 부족합니다:
 * 충전에 7:00:00 필요, 가능한 시간은 2:00:00."처럼 이미 무엇을 고쳐야 하는지 말해 준다.
 * 이걸 "오류가 발생했습니다"로 덮으면 사용자가 할 수 있는 일이 사라진다.
 */
export function ResultErrorState({
  message,
  query,
  onRetry,
}: {
  message: string;
  query: string;
  onRetry: () => void;
}) {
  return (
    <Card className="p-6 shadow-panel lg:p-8">
      <h2 className="text-section">추천을 불러오지 못했어요</h2>
      {/* 검증 실패가 여러 건이면 줄바꿈으로 이어져 온다 (client.ts) — 줄을 살려 둔다. */}
      <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-2">{message}</p>

      <div className="mt-6 flex flex-wrap gap-3">
        <ButtonLink href={`/recommend?${query}`} variant="primary">
          조건 고치기
        </ButtonLink>
        <Button type="button" variant="outline" onClick={onRetry}>
          다시 시도
        </Button>
      </div>
    </Card>
  );
}

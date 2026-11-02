"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api/client";
import type { SavedPlan } from "@/lib/api/types";
import { formatHm, formatKoreanDate, formatSignedWon, formatWon } from "@/lib/format";

import { vehicleLabel } from "./plan-view";

/**
 * 저장한 계획 목록.
 *
 * 모바일은 카드, 데스크톱은 표다 (디자인 p-11 / p-23). 두 벌을 따로 그리지 않고
 * 같은 DOM에 `lg:contents`를 걸어 열로 펼친다 — 같은 값을 두 번 그리면 스크린리더가
 * 두 번 읽고, 언젠가 한쪽만 고쳐서 두 화면이 다른 금액을 보여주게 된다.
 *
 * 열이 바뀌는 곳은 GRID_COLUMNS 한 줄뿐이라 머리글과 각 줄이 어긋날 수 없다.
 */
const GRID_COLUMNS =
  "grid-cols-[minmax(0,1fr)_auto] " +
  "lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1.2fr)_minmax(0,0.9fr)_minmax(0,0.9fr)_auto]";

export function PlanRecordList({
  items,
  onDelete,
}: {
  items: SavedPlan[];
  /** 실패하면 던진다 — 줄이 그 메시지를 자기 자리에 보여준다. */
  onDelete: (id: string) => Promise<void>;
}) {
  return (
    <div className="mt-4 lg:mt-5 lg:overflow-hidden lg:rounded-card lg:border lg:border-line lg:bg-surface">
      <div
        data-testid="plan-table-header"
        className={`hidden lg:grid ${GRID_COLUMNS} gap-x-4 border-b border-line bg-sunken/40 px-5 py-3 text-sm font-bold text-ink-2`}
      >
        <span>충전 날짜</span>
        <span>차량</span>
        <span>추천 시간</span>
        <span>예상 비용</span>
        <span>절감</span>
        <span className="sr-only">삭제</span>
      </div>

      <ul className="space-y-3 lg:space-y-0">
        {items.map((plan) => (
          <PlanRecordRow key={plan.id} plan={plan} onDelete={onDelete} />
        ))}
      </ul>
    </div>
  );
}

function PlanRecordRow({
  plan,
  onDelete,
}: {
  plan: SavedPlan;
  onDelete: (id: string) => Promise<void>;
}) {
  // 확인 단계는 줄마다 따로 둔다. window.confirm은 쓰지 않는다 — 브라우저 모달은
  // 화면 밖에 떠서 자동화도, 스크린리더 흐름도 끊는다.
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /*
   * 앞에 세우는 날짜는 **충전하는 날**이다 (charge_start). 저장한 날이 아니다.
   * 목록의 월 선택과 정렬이 이 값을 기준으로 돌기 때문에, 여기에 저장일을 쓰면
   * "10월을 골랐는데 9월 날짜가 보이는" 화면이 된다.
   */
  const date = formatKoreanDate(plan.charge_start);
  const savedOn = formatKoreanDate(plan.created_at);
  const time = `${formatHm(plan.result.best.start)} – ${formatHm(plan.result.best.end)}`;

  async function remove() {
    setDeleting(true);
    setError(null);
    try {
      await onDelete(plan.id);
      // 성공하면 이 줄은 목록에서 빠진다. 상태를 되돌릴 필요가 없다.
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "기록을 지우지 못했습니다.");
      setDeleting(false);
      setConfirming(false);
    }
  }

  return (
    <li className="rounded-card bg-surface p-4 lg:rounded-none lg:border-t lg:border-line lg:bg-transparent lg:px-5 lg:py-4 lg:first:border-t-0">
      <div className={`grid ${GRID_COLUMNS} items-center gap-x-3 lg:gap-x-4`}>
        {/* lg에서 이 껍데기들이 사라지고 안의 값들이 그대로 표의 열이 된다. */}
        <div className="min-w-0 lg:contents">
          <div className="flex min-w-0 items-baseline gap-1.5 lg:contents">
            <p className="text-sm text-ink-2 lg:text-ink">{date}</p>
            <span className="text-sm text-ink-2 lg:hidden" aria-hidden>
              ·
            </span>
            <p className="truncate text-sm text-ink-2">{vehicleLabel(plan)}</p>
          </div>

          {/* 저장일은 버리지 않는다 — "언제 세운 계획인지"도 알아야 한다. */}
          <p className="mt-0.5 text-sm text-ink-2 lg:hidden">{savedOn}에 저장</p>

          <p className="mt-1 text-xl font-bold tnum lg:mt-0 lg:text-base">{time}</p>

          <div className="mt-1 flex flex-wrap items-baseline gap-1.5 lg:contents">
            <span className="text-sm text-ink-2 lg:hidden">예상</span>
            <p className="text-sm tnum text-ink-2 lg:text-ink">
              {formatWon(plan.result.best.cost_won)}
            </p>
            <span className="text-sm text-ink-2 lg:hidden" aria-hidden>
              ·
            </span>
            <p className="text-sm font-bold tnum text-band-light">
              {formatSignedWon(plan.result.savings_won)}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setConfirming(true)}
          aria-label={`${date} ${time} 기록 삭제`}
          className="justify-self-end inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-ink-2 transition-colors duration-150 hover:text-danger
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand
            "
        >
          <TrashIcon className="size-5 lg:hidden" />
          <span className="hidden text-sm font-bold text-danger lg:inline">삭제</span>
        </button>
      </div>

      {confirming ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-2 rounded-field bg-sunken px-3.5 py-3">
          <p className="text-sm font-bold">정말 삭제할까요?</p>
          <p className="text-sm text-ink-2">되돌릴 수 없어요.</p>
          <div className="ml-auto flex gap-2">
            <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
              취소
            </Button>
            <Button
              type="button"
              variant="dark"
              disabled={deleting}
              onClick={() => void remove()}
              className="bg-danger hover:bg-danger/90 active:bg-danger/80"
            >
              {deleting ? "지우는 중…" : "네, 삭제할게요"}
            </Button>
          </div>
        </div>
      ) : null}

      {/* 실패 사유는 백엔드 문장을 그대로 쓴다 (남의 기록이면 404). */}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function TrashIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M4.5 6.6h15M9.6 6.6V4.8h4.8v1.8" />
        <path d="M6.6 6.6 7.5 19a.9.9 0 0 0 .9.8h7.2a.9.9 0 0 0 .9-.8l.9-12.4" />
        <path d="M10.4 10.2v6M13.6 10.2v6" />
      </g>
    </svg>
  );
}

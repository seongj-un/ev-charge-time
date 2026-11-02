"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { Vehicle } from "@/lib/api/types";

import { DangerButton } from "./MeStates";

import { vehicleSpecLine } from "./me-format";

/**
 * 차량 카드 목록 (디자인 p-09 · p-22).
 *
 * 삭제 확인 상태만 이 컴포넌트가 직접 들고 있다. 화면 전체 state로 올리면 목록을
 * 다시 불러올 때마다 "어느 카드가 물어보는 중이었나"를 같이 관리해야 하는데,
 * 여기 두면 지워진 차의 id는 다음 렌더에서 그냥 사라진다.
 *
 * window.confirm은 쓰지 않는다 — 브라우저 모달은 자동화가 넘지 못하고, 무엇을
 * 지우는지도 카드 옆에서 보여주는 편이 훨씬 분명하다.
 */
export function VehicleList({
  vehicles,
  busyId,
  onEdit,
  onMakeDefault,
  onDelete,
}: {
  vehicles: Vehicle[];
  /** 요청이 나가 있는 차량. 같은 버튼을 두 번 누르는 걸 막는다. */
  busyId: string | null;
  onEdit: (vehicle: Vehicle) => void;
  onMakeDefault: (vehicle: Vehicle) => void;
  onDelete: (vehicle: Vehicle) => void;
}) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  return (
    <ul className="grid gap-3">
      {vehicles.map((vehicle) => {
        const busy = busyId === vehicle.id;
        const confirming = confirmingId === vehicle.id;
        return (
          <li
            key={vehicle.id}
            className={`rounded-card bg-surface p-4 lg:p-5 ${
              vehicle.is_default ? "border-2 border-brand" : "border border-line"
            }`}
          >
            <div className="lg:flex lg:items-center lg:justify-between lg:gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="truncate text-base font-bold text-ink">{vehicle.name}</h3>
                  {vehicle.is_default ? <Badge tone="ok">기본</Badge> : null}
                </div>
                <p className="tnum mt-1.5 text-sm text-ink-2">{vehicleSpecLine(vehicle)}</p>
              </div>

              {confirming ? (
                <div className="mt-3 lg:mt-0 lg:shrink-0 lg:text-right">
                  <p className="text-sm font-bold text-ink">정말 삭제할까요?</p>
                  <p className="mt-0.5 text-sm text-ink-2">되돌릴 수 없어요.</p>
                  <div className="mt-2 flex gap-2">
                    <DangerButton
                      tone="outline"
                      className="flex-1 lg:flex-none"
                      disabled={busy}
                      onClick={() => onDelete(vehicle)}
                    >
                      삭제할게요
                    </DangerButton>
                    <Button
                      type="button"
                      variant="ghost"
                      className="flex-1 lg:flex-none"
                      onClick={() => setConfirmingId(null)}
                    >
                      취소
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex gap-2 lg:mt-0 lg:shrink-0">
                  {/* 기본 차량에는 "기본으로"가 없다 — 눌러도 아무 일이 없는 버튼은 두지 않는다. */}
                  {vehicle.is_default ? null : (
                    <Button
                      type="button"
                      variant="outline"
                      className="flex-1 lg:flex-none"
                      disabled={busy}
                      onClick={() => onMakeDefault(vehicle)}
                    >
                      기본으로
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1 lg:flex-none"
                    disabled={busy}
                    onClick={() => onEdit(vehicle)}
                  >
                    수정
                  </Button>
                  {/* 모바일은 테두리 있는 버튼(p-09), 데스크톱은 글씨만(p-22) */}
                  <DangerButton
                    tone="outline"
                    className="flex-1 lg:flex-none lg:border-transparent lg:bg-transparent"
                    disabled={busy}
                    onClick={() => setConfirmingId(vehicle.id)}
                  >
                    삭제
                  </DangerButton>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

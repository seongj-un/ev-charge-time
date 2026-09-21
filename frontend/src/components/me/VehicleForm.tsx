"use client";

import { useState, type FormEvent } from "react";

import { ChevronLeftIcon } from "@/components/shell/icons";
import { Button } from "@/components/ui/Button";
import { Field, SelectField } from "@/components/ui/Field";
import { ApiError } from "@/lib/api/client";
import { MODE_LABEL, type Mode, type Vehicle, type VehicleInput } from "@/lib/api/types";

/**
 * 차량 추가·수정 폼 (디자인 p-10 모바일 · p-22 데스크톱 우측 카드).
 *
 * 숫자를 문자열로 들고 있는다. 숫자 state로 두면 칸을 비우는 순간 NaN이 되어
 * "지우고 다시 치기"가 막힌다. 숫자로 바꾸는 건 제출 직전 한 번뿐이다.
 *
 * 추가와 수정을 한 컴포넌트로 쓴다. 부모가 key를 바꿔 다시 마운트시키므로
 * 안쪽 state를 initial에 맞춰 되돌리는 코드가 아예 필요 없다 —
 * "수정을 열었는데 앞 차량 값이 남아 있다" 부류의 버그가 생길 자리가 없다.
 *
 * 충전 방식은 모바일 시안이 세그먼티드지만 양쪽 다 select를 쓴다. 두 컨트롤을
 * 겹쳐 두고 CSS로 하나씩 숨기면 스크린리더에는 같은 질문이 두 번 읽히고,
 * 라디오 그룹과 select 중 어느 쪽이 정본인지도 흐려진다.
 */

type Errors = Partial<Record<"name" | "battery" | "charger", string>>;

const MODE_OPTIONS: Mode[] = ["self_low", "self_high", "public_fast"];

export function VehicleForm({
  initial = null,
  onSubmit,
  onCancel,
  className = "",
}: {
  /** 수정할 차량. null이면 추가 폼이다. */
  initial?: Vehicle | null;
  /** 성공하면 resolve, 실패하면 reject — 실패 메시지는 이 폼이 직접 띄운다. */
  onSubmit: (input: VehicleInput) => Promise<void>;
  onCancel: () => void;
  className?: string;
}) {
  const editing = initial !== null;
  const [name, setName] = useState(initial?.name ?? "");
  const [battery, setBattery] = useState(initial ? String(initial.battery_kwh) : "");
  const [charger, setCharger] = useState(initial ? String(initial.charger_kw) : "");
  const [mode, setMode] = useState<Mode>(initial?.mode ?? "self_low");
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const batteryKwh = Number(battery);
    const chargerKw = Number(charger);
    const next: Errors = {};
    if (name.trim() === "") next.name = "별칭을 입력해 주세요.";
    if (!Number.isFinite(batteryKwh) || batteryKwh <= 0) {
      next.battery = "배터리 용량을 0보다 큰 숫자로 입력해 주세요.";
    }
    if (!Number.isFinite(chargerKw) || chargerKw <= 0) {
      next.charger = "충전기 출력을 0보다 큰 숫자로 입력해 주세요.";
    }
    setErrors(next);
    // 서버가 422로 되돌려줄 것을 미리 잡는다. 왕복 한 번을 사용자에게 시키지 않는다.
    if (Object.keys(next).length > 0) return;

    setPending(true);
    setFailure(null);
    try {
      await onSubmit({
        name: name.trim(),
        battery_kwh: batteryKwh,
        charger_kw: chargerKw,
        mode,
        is_default: isDefault,
      });
    } catch (error: unknown) {
      setFailure(error instanceof ApiError ? error.message : "저장하지 못했습니다.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void handleSubmit(event)}
      className={`rounded-card border border-line bg-surface p-5 lg:p-6 ${className}`}
    >
      <div className="flex items-center gap-1">
        {/* 모바일에서는 이 폼이 화면을 덮는다 — 목록으로 돌아갈 길이 필요하다. */}
        <button
          type="button"
          onClick={onCancel}
          aria-label="목록으로"
          className="-ml-2 rounded-pill p-1.5 text-ink transition-colors hover:bg-sunken lg:hidden"
        >
          <ChevronLeftIcon />
        </button>
        <h2 className="text-lg font-bold text-ink">{editing ? "차량 수정" : "차량 추가"}</h2>
      </div>

      <Field
        label="별칭"
        placeholder="예: 출퇴근 차"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={errors.name}
        className="mt-5"
      />

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Field
          label="배터리 (kWh)"
          type="number"
          inputMode="decimal"
          min={1}
          step="any"
          value={battery}
          onChange={(event) => setBattery(event.target.value)}
          error={errors.battery}
        />
        <Field
          label="충전기 출력 (kW)"
          type="number"
          inputMode="decimal"
          min={0.1}
          step="any"
          value={charger}
          onChange={(event) => setCharger(event.target.value)}
          error={errors.charger}
        />
      </div>

      <SelectField
        label="기본 충전 방식"
        value={mode}
        onChange={(event) => setMode(event.target.value as Mode)}
        className="mt-4"
      >
        {MODE_OPTIONS.map((value) => (
          <option key={value} value={value}>
            {MODE_LABEL[value]}
          </option>
        ))}
      </SelectField>

      <label className="mt-5 flex cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          checked={isDefault}
          onChange={(event) => setIsDefault(event.target.checked)}
          className="size-5 rounded-[6px] accent-brand"
        />
        <span className="text-sm font-bold text-ink">기본 차량으로 설정</span>
      </label>

      {failure ? (
        <p role="alert" className="mt-4 rounded-field bg-warn-bg px-3.5 py-3 text-sm text-warn-fg">
          {failure}
        </p>
      ) : null}

      <div className="mt-5 flex gap-2">
        <Button type="submit" size="lg" className="flex-1" disabled={pending}>
          저장
        </Button>
        {/*
         * 데스크톱의 상시 "차량 추가" 카드에는 취소가 어색하다 — 돌아갈 곳이 없다.
         * 수정 중일 때와 모바일에서는 반드시 필요하다.
         */}
        <Button
          type="button"
          variant="ghost"
          size="lg"
          onClick={onCancel}
          className={editing ? "" : "lg:hidden"}
        >
          취소
        </Button>
      </div>
    </form>
  );
}

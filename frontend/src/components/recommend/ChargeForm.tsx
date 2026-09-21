"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore, type FormEvent } from "react";

import { useSession, type SessionStatus } from "@/components/auth/SessionProvider";
import { Button } from "@/components/ui/Button";
import { Field, SelectField } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { MODE_LABEL, type Mode, type Vehicle } from "@/lib/api/types";
import { estimateHours, requiredEnergyKwh } from "@/lib/charging";
import { formatDuration, formatKwh } from "@/lib/format";
import { defaultForm, toSearchParams, type RecommendForm } from "@/lib/recommend-params";

import { useMyVehicles } from "./useMyVehicles";

/**
 * 충전 조건 입력 폼.
 *
 * 값을 숫자가 아니라 문자열로 들고 있는다. 숫자로 들면 칸을 비우는 순간 NaN이 되어
 * "지우고 다시 치기"가 막힌다. 숫자로 바꾸는 건 요약 계산과 제출 직전뿐이다.
 *
 * 시각 두 칸만 null을 허용한다 — "아직 아무도 손대지 않았다"는 뜻이고, 그동안은
 * 마운트 뒤에 계산한 기본 시각을 보여준다(아래 useDefaultTimes).
 */
type Draft = {
  batteryKwh: string;
  chargerKw: string;
  socNow: string;
  socTarget: string;
  earliestStart: string | null;
  deadline: string | null;
  mode: Mode;
};

/** 기본 시각까지 채워 넣은, 화면에 실제로 그려지는 값 */
type Conditions = Omit<Draft, "earliestStart" | "deadline"> & {
  earliestStart: string;
  deadline: string;
};

type Errors = Partial<Record<keyof Draft, string>>;

/** 디자인 순서 그대로. 이름표는 백엔드와 공유하는 MODE_LABEL에서 가져온다. */
const MODE_OPTIONS: { value: Mode; label: string }[] = [
  { value: "self_low", label: MODE_LABEL.self_low },
  { value: "self_high", label: MODE_LABEL.self_high },
  { value: "public_fast", label: MODE_LABEL.public_fast },
];

/** 숫자 기본값은 defaultForm이 정한 것을 그대로 쓴다 — 기본값이 두 군데 생기지 않게. */
function initialDraft(): Draft {
  const base = defaultForm(new Date(0));
  return {
    batteryKwh: String(base.batteryKwh),
    chargerKw: String(base.chargerKw),
    socNow: String(base.socNow),
    socTarget: String(base.socTarget),
    earliestStart: null,
    deadline: null,
    mode: base.mode,
  };
}

const NEVER_CHANGES = () => () => {};

/**
 * 마운트된 뒤에만 '지금'을 읽는다.
 *
 * 서버가 그린 시각과 브라우저가 그린 시각은 어차피 다르다 — 렌더 시점도, 표준시도.
 * 첫 렌더에 그 값을 쓰면 hydration 불일치가 난다. useSyncExternalStore는 서버 렌더와
 * hydration 때 getServerSnapshot(null)을 쓰고, 마운트가 끝난 뒤에야 getSnapshot으로
 * 넘어간다. 그래서 서버 HTML과 첫 클라이언트 렌더가 글자 하나까지 같다.
 *
 * 스냅샷은 처음 한 번만 만들어 가둬 둔다. 렌더마다 새 값을 돌려주면 React가 계속 다시
 * 그린다. 폼이 다시 마운트되면 그때 다시 계산된다 — 어제 열어둔 탭의 시각이 남지 않는다.
 */
function useDefaultTimes(): RecommendForm | null {
  const [readNow] = useState(() => {
    let snapshot: RecommendForm | null = null;
    return (): RecommendForm => {
      snapshot ??= defaultForm(new Date());
      return snapshot;
    };
  });
  return useSyncExternalStore(NEVER_CHANGES, readNow, () => null);
}

/** "출퇴근 차 · 77 kWh · 11 kW (기본)" */
function vehicleOptionLabel(vehicle: Vehicle): string {
  const spec = `${vehicle.battery_kwh} kWh · ${vehicle.charger_kw} kW`;
  return vehicle.is_default
    ? `${vehicle.name} · ${spec} (기본)`
    : `${vehicle.name} · ${spec}`;
}

/**
 * 차량 칸 아래 안내.
 *
 * 손님에게 "로그인 후 불러옵니다"라고만 하면 그다음 할 일을 모른다. 상태마다
 * 지금 할 수 있는 일을 적는다.
 */
function vehicleHintFor(
  status: SessionStatus,
  count: number,
  loaded: boolean,
): string {
  if (status === "unreachable") {
    return "서버에 연결하지 못해 저장한 차량을 불러오지 못했어요. 값을 직접 입력하면 추천은 그대로 받을 수 있어요.";
  }
  if (status !== "authenticated") {
    return "로그인하면 저장한 차량을 불러와요. 로그인 없이 값을 직접 입력해도 추천은 받을 수 있어요.";
  }
  if (!loaded) return "저장한 차량을 불러오는 중이에요.";
  if (count === 0) {
    return "저장한 차량이 아직 없어요. 차량을 추가하면 다음부터 값이 자동으로 채워져요.";
  }
  return "차량을 고르면 배터리 용량·충전기 출력·충전 방식이 채워져요.";
}

export function ChargeForm() {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>(initialDraft);
  /** 제출을 한 번이라도 눌렀는지. 누르기 전에는 빨간 글씨를 띄우지 않는다. */
  const [submitted, setSubmitted] = useState(false);
  const defaults = useDefaultTimes();

  const { status } = useSession();
  const { vehicles, loaded: vehiclesLoaded } = useMyVehicles();
  const [vehicleId, setVehicleId] = useState("");
  /**
   * 차량 값이 실린 칸을 사용자가 건드렸는지.
   *
   * 차량 목록은 마운트 뒤에 도착한다. 그 사이 이미 고쳐 둔 값을 기본 차량으로
   * 덮어쓰면 방금 친 숫자가 눈앞에서 바뀐다.
   */
  const [specTouched, setSpecTouched] = useState(false);

  const conditions: Conditions = {
    ...draft,
    earliestStart: draft.earliestStart ?? defaults?.earliestStart ?? "",
    deadline: draft.deadline ?? defaults?.deadline ?? "",
  };

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  /** 차량이 정해 주는 칸을 직접 고치면, 그 뒤로는 기본 차량이 끼어들지 않는다. */
  const setSpec = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setSpecTouched(true);
    set(key, value);
  };

  function applyVehicle(vehicle: Vehicle) {
    setDraft((prev) => ({
      ...prev,
      batteryKwh: String(vehicle.battery_kwh),
      chargerKw: String(vehicle.charger_kw),
      mode: vehicle.mode,
    }));
  }

  function pickVehicle(id: string) {
    setVehicleId(id);
    setSpecTouched(true);
    const vehicle = vehicles.find((candidate) => candidate.id === id);
    // 직접 입력으로 되돌릴 때 칸을 비우지 않는다. 고른 차의 값에서 조금만
    // 고쳐 쓰는 경우가 흔한데, 비우면 처음부터 다시 쳐야 한다.
    if (vehicle) applyVehicle(vehicle);
  }

  // 기본 차량을 처음 한 번만 채운다. 사용자가 이미 손댔으면 끼어들지 않는다.
  const defaultVehicle = vehicles.find((vehicle) => vehicle.is_default);
  if (defaultVehicle && vehicleId === "" && !specTouched) {
    setVehicleId(defaultVehicle.id);
    applyVehicle(defaultVehicle);
  }

  const canPickVehicle = vehicles.length > 0;
  const vehicleHint = vehicleHintFor(status, vehicles.length, vehiclesLoaded);
  const loggedIn = status === "authenticated";
  const vehicleLinkHref = loggedIn ? "/me/vehicles" : `/login?next=${encodeURIComponent("/recommend")}`;
  const vehicleLinkLabel = loggedIn ? (canPickVehicle ? "차량 관리" : "차량 추가") : "로그인";

  // 칸이 일곱 개뿐이라 렌더마다 다시 검사해도 된다. 대신 고치는 즉시 오류가 사라진다.
  const { errors, form: validated } = validate(conditions);
  /*
   * 고른 차량을 결과 화면까지 들고 간다. 저장할 때 vehicle_id를 보내야
   * SavedPlan.vehicle_name이 채워지고, 그래야 충전 기록이 "어느 차로 세운
   * 계획인지"를 안다. 추천 요청에는 안 실린다 (recommend-params 참고).
   */
  const form = validated && vehicleId ? { ...validated, vehicleId } : validated;
  const shown: Errors = submitted ? errors : {};

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    if (!form) return;
    // 조건을 URL에 실어 넘긴다 — 결과 화면에서 새로고침해도, 링크를 공유해도 살아 있다.
    router.push(`/recommend/result?${toSearchParams(form)}`);
  }

  return (
    <form
      noValidate
      onSubmit={handleSubmit}
      /*
       * 데스크톱에서만 폼 전체가 흰 카드다(시안 p-15). 모바일 시안은 캔버스 위에
       * 바로 놓이므로, 항상 카드로 보이는 Card 대신 lg: 접두사를 붙인 클래스를 쓴다.
       */
      className="pb-2 lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-8"
    >
      <h2 className="hidden lg:block mb-6 text-2xl font-bold tracking-tight">충전 조건 입력</h2>

      {/* SelectField가 라벨을 직접 그리므로, 같은 줄 오른쪽에 링크를 얹는다. */}
      <div className="relative">
        <SelectField
          label="내 차량"
          value={vehicleId}
          onChange={(event) => pickVehicle(event.target.value)}
          disabled={!canPickVehicle}
          /* 못 누르는 칸이 눌리는 칸처럼 보이면 안 된다. 공유 컴포넌트는 못 고치니 여기서 입힌다. */
          className={canPickVehicle ? "" : "[&_select]:cursor-not-allowed [&_select]:text-ink-3"}
          hint={vehicleHint}
        >
          <option value="">차량 정보 직접 입력</option>
          {vehicles.map((vehicle) => (
            <option key={vehicle.id} value={vehicle.id}>
              {vehicleOptionLabel(vehicle)}
            </option>
          ))}
        </SelectField>
        <Link
          href={vehicleLinkHref}
          className="absolute right-0 top-0 text-sm font-bold text-brand underline underline-offset-4 hover:text-brand/80"
        >
          {vehicleLinkLabel}
        </Link>
      </div>

      {/*
       * 모바일 시안에는 이 두 칸이 없다. 차량 선택이 아직 501이라 어디선가 받지 않으면
       * 추천 자체를 못 하므로, 차량 선택 바로 아래(= 차량 정보 자리)에 그대로 노출한다.
       */}
      <div className="mt-5 grid grid-cols-2 gap-3 lg:gap-5">
        <Field
          label="배터리 용량"
          suffix="kWh"
          inputMode="decimal"
          value={conditions.batteryKwh}
          onChange={(event) => setSpec("batteryKwh", event.target.value)}
          error={shown.batteryKwh}
        />
        <Field
          label="충전기 출력"
          suffix="kW"
          inputMode="decimal"
          value={conditions.chargerKw}
          onChange={(event) => setSpec("chargerKw", event.target.value)}
          error={shown.chargerKw}
        />
      </div>

      <SegmentedControl
        className="mt-5"
        name="mode"
        label="충전 방식"
        value={conditions.mode}
        options={MODE_OPTIONS}
        onChange={(mode) => setSpec("mode", mode)}
      />

      {/* 모바일 시안은 이 네 칸만 흰 카드로 묶는다. 데스크톱은 바깥 카드 하나뿐이라 배경을 지운다. */}
      <div className="mt-5 rounded-card border border-line bg-surface p-4 lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0">
        <div className="grid grid-cols-2 gap-3 lg:gap-5">
          <Field
            label="현재 충전량"
            suffix="%"
            inputMode="decimal"
            value={conditions.socNow}
            onChange={(event) => set("socNow", event.target.value)}
            error={shown.socNow}
          />
          <Field
            label="목표 충전량"
            suffix="%"
            inputMode="decimal"
            value={conditions.socTarget}
            onChange={(event) => set("socTarget", event.target.value)}
            error={shown.socTarget}
          />
        </div>

        <div className="mt-4 grid gap-4 lg:mt-5 lg:grid-cols-2 lg:gap-5">
          <Field
            label="충전 시작 가능"
            type="datetime-local"
            value={conditions.earliestStart}
            onChange={(event) => set("earliestStart", event.target.value)}
            error={shown.earliestStart}
          />
          <Field
            label="이때까지 완료"
            type="datetime-local"
            value={conditions.deadline}
            onChange={(event) => set("deadline", event.target.value)}
            error={shown.deadline}
          />
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-4 lg:mt-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex items-baseline justify-between gap-3 lg:block">
          <p className="text-sm text-ink-3">필요 충전량</p>
          <p className="tnum text-base font-bold lg:mt-1.5 lg:text-lg" aria-live="polite">
            {summarize(conditions)}
          </p>
        </div>
        <Button type="submit" size="lg" className="w-full lg:w-auto">
          최적 시간 찾기
        </Button>
      </div>
    </form>
  );
}

/**
 * "21 kWh · 약 3시간".
 *
 * 서버에 묻지 않고 여기서 센다 — 키 하나 칠 때마다 왕복이 생기면 이 줄이 늦게 따라온다.
 * 출력이 아직 비어 있으면 시간은 빼고 충전량만 보여준다.
 */
function summarize(conditions: Conditions): string {
  const energyKwh = requiredEnergyKwh({
    batteryKwh: parseNumber(conditions.batteryKwh) ?? 0,
    socNow: parseNumber(conditions.socNow) ?? 0,
    socTarget: parseNumber(conditions.socTarget) ?? 0,
  });
  const hours = estimateHours({ energyKwh, chargerKw: parseNumber(conditions.chargerKw) ?? 0 });
  // 채울 게 없으면(목표 ≤ 현재) "약 0분"은 답이 아니라 잡음이다. 충전량만 보여준다.
  return hours === null || energyKwh === 0
    ? formatKwh(energyKwh)
    : `${formatKwh(energyKwh)} · ${formatDuration(hours)}`;
}

/**
 * 제출 전에 여기서 걸러낸다. 서버도 422로 막아주지만, 왕복을 기다렸다 알려주면
 * 사용자는 이미 결과 화면을 기대하고 있다. 틀린 칸 바로 밑에 붙여 주는 편이 빠르다.
 */
function validate(conditions: Conditions): { errors: Errors; form: RecommendForm | null } {
  const errors: Errors = {};

  const batteryKwh = parseNumber(conditions.batteryKwh);
  if (batteryKwh === null || batteryKwh <= 0) {
    errors.batteryKwh = "배터리 용량을 0보다 크게 입력해 주세요";
  }

  const chargerKw = parseNumber(conditions.chargerKw);
  if (chargerKw === null || chargerKw <= 0) {
    errors.chargerKw = "충전기 출력을 0보다 크게 입력해 주세요";
  }

  // 이미 100%인 차는 충전할 게 없고, 목표가 100%를 넘을 수는 없다 (API 명세서 2-2).
  const socNow = parseNumber(conditions.socNow);
  if (socNow === null || socNow < 0 || socNow >= 100) {
    errors.socNow = "현재 충전량은 0 이상 100 미만이어야 해요";
  }

  const socTarget = parseNumber(conditions.socTarget);
  if (socTarget === null || socTarget <= 0 || socTarget > 100) {
    errors.socTarget = "목표 충전량은 100 이하여야 해요";
  } else if (socNow !== null && socTarget <= socNow) {
    errors.socTarget = "목표 충전량은 현재보다 커야 해요";
  }

  if (!conditions.earliestStart) {
    errors.earliestStart = "충전 시작 가능 시각을 입력해 주세요";
  }

  if (!conditions.deadline) {
    errors.deadline = "완료 시각을 입력해 주세요";
  } else if (conditions.earliestStart && conditions.deadline <= conditions.earliestStart) {
    // "YYYY-MM-DDTHH:mm"은 자리 수가 고정이라 문자열끼리 비교해도 시간순이 된다.
    // Date로 바꾸면 표준시 해석만 끼어들 뿐, 여기서 얻을 게 없다.
    errors.deadline = "완료 시각은 시작 시각보다 뒤여야 해요";
  }

  const complete =
    Object.keys(errors).length === 0 &&
    batteryKwh !== null &&
    chargerKw !== null &&
    socNow !== null &&
    socTarget !== null;

  return {
    errors,
    form: complete
      ? {
          batteryKwh,
          chargerKw,
          socNow,
          socTarget,
          earliestStart: conditions.earliestStart,
          deadline: conditions.deadline,
          mode: conditions.mode,
        }
      : null,
  };
}

/** 빈 칸을 0으로 읽지 않으려고 Number()를 그냥 쓰지 않는다. */
function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

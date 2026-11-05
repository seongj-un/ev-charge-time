"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { ChevronLeftIcon, ChevronRightIcon } from "@/components/shell/icons";

/**
 * 날짜 + 시각 입력. 값은 datetime-local과 같은 "YYYY-MM-DDTHH:mm"(한국 벽시계)이다.
 *
 * 브라우저 기본 datetime-local을 쓰지 않는 이유: 크롬의 달력 팝업은 앱과 글꼴·색이
 * 따로 놀고, 칸에는 "2026. 11. 05. 오후 (" 처럼 값이 잘려 보였다. 시연 화면에서
 * 가장 먼저 손대는 칸이라 직접 그린다.
 *
 * 구성: [날짜 버튼 → 달력 팝오버] [시각 select(30분 간격)].
 * 시각은 네이티브 select로 둔다 — 모바일에서 휠 피커가 뜨고, 키보드·스크린리더가 그대로 된다.
 */

/** 공휴일 목록(backend/config/holidays.yaml)이 있는 해. 백엔드는 다른 해를 거절한다. */
const SUPPORTED_YEARS = { first: 2026, last: 2027 } as const;

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"] as const;

const STEP_MINUTES = 30;
const TIME_OPTIONS = Array.from({ length: (24 * 60) / STEP_MINUTES }, (_, index) => {
  const minutes = index * STEP_MINUTES;
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
});

type Ymd = { year: number; month: number; day: number };

export function DateTimeField({
  label,
  value,
  onChange,
  error,
  today,
  minDay,
  className = "",
}: {
  label: string;
  /** "YYYY-MM-DDTHH:mm". 아직 기본값을 못 정했으면 "" */
  value: string;
  onChange: (value: string) => void;
  error?: string;
  /** "YYYY-MM-DD" (한국 날짜). '오늘' 표시와 바로가기에 쓴다. 모르면 생략 */
  today?: string;
  /** "YYYY-MM-DD". 이보다 앞선 날은 달력에서 고를 수 없다(지난 날짜 막기). 생략하면 제한 없음 */
  minDay?: string;
  className?: string;
}) {
  const id = useId();
  const labelId = `${id}-label`;
  const errorId = `${id}-error`;
  const dialogId = `${id}-dialog`;

  const [datePart, timePart] = value ? value.split("T") : ["", ""];
  const selected = parseYmd(datePart);

  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // 바깥을 누르면 닫는다.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function pickDay(day: string) {
    onChange(`${day}T${timePart || "00:00"}`);
    close();
  }

  // 30분 간격에 안 맞는 값(예: 주소창으로 넘어온 21:37)도 선택지에서 사라지지 않게 끼워 넣는다.
  const timeOptions =
    timePart && !TIME_OPTIONS.includes(timePart) ? [...TIME_OPTIONS, timePart].sort() : TIME_OPTIONS;

  const relative = selected && today ? relativeLabel(datePart, today) : null;
  // 올해가 아니면 연도를 붙인다. 12월에 1월을 고르면 "1월 5일"만으로는 몇 년인지 모른다.
  const todayYmd = parseYmd(today ?? "");
  const showYear = selected !== null && todayYmd !== null && selected.year !== todayYmd.year;

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <span id={labelId} className="mb-2 block text-sm font-bold text-ink">
        {label}
      </span>

      <div
        role="group"
        aria-labelledby={labelId}
        data-value={value}
        className="grid grid-cols-[minmax(0,1fr)_5.75rem] gap-2 sm:grid-cols-[minmax(0,1fr)_8rem]"
      >
        <button
          ref={triggerRef}
          type="button"
          aria-label={`${label} 날짜, ${selected ? formatLong(selected) : "선택 안 됨"}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? dialogId : undefined}
          aria-describedby={error ? errorId : undefined}
          // 폼이 제출을 막을 때 첫 번째 틀린 칸으로 초점을 옮기는 표시 (ChargeForm)
          data-invalid={error ? true : undefined}
          onClick={() => setOpen((prev) => !prev)}
          onKeyDown={(event) => {
            if (event.key === "Escape" && open) {
              event.preventDefault();
              setOpen(false);
            }
          }}
          className={`flex h-12 min-w-0 items-center gap-2 rounded-field border bg-field px-3.5 text-left sm:gap-2.5 sm:px-4 text-ink transition-colors duration-150
            hover:border-ink-3 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-brand
            ${open ? "border-brand" : error ? "border-danger" : "border-line"}`}
        >
          {/* 400px 아래에서는 아이콘을 빼 날짜·요일이 잘리지 않게 한다 (360px 폰에서 9px 모자랐다) */}
          <CalendarIcon className="size-[18px] shrink-0 text-brand max-[399px]:hidden sm:size-5" />
          {selected ? (
            <span className="min-w-0 truncate font-bold">{formatShort(selected, showYear)}</span>
          ) : (
            <span className="h-4 w-24 animate-pulse rounded bg-sunken" aria-hidden />
          )}
          {relative ? (
            <span className="ml-auto shrink-0 rounded-pill bg-brand-soft px-1.5 py-0.5 text-sm font-bold text-brand sm:px-2">
              {relative}
            </span>
          ) : null}
        </button>

        <div className="relative">
          <select
            aria-label={`${label} 시각`}
            value={timePart}
            disabled={!selected}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            onChange={(event) => onChange(`${datePart}T${event.target.value}`)}
            className={`tnum h-12 w-full cursor-pointer appearance-none rounded-field border bg-field pr-8 pl-3 font-bold sm:pr-9 sm:pl-4 text-ink transition-colors duration-150
              hover:border-ink-3 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-brand
              disabled:cursor-not-allowed disabled:opacity-60 ${error ? "border-danger" : "border-line"}`}
          >
            {!timePart ? <option value="">--:--</option> : null}
            {timeOptions.map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>
          <ChevronDownIcon className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-ink-2 sm:right-3" />
        </div>
      </div>

      {error ? (
        <p id={errorId} className="mt-2 text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}

      {open ? (
        <CalendarPopover
          id={dialogId}
          label={label}
          selected={selected}
          today={todayYmd}
          minDay={parseYmd(minDay ?? "")}
          onPick={(day) => pickDay(formatYmd(day))}
          onClose={close}
          onFocusLeave={(next) => {
            // Tab·Shift+Tab으로 달력 밖으로 나가면 닫는다. 그대로 두면 아래 칸과 제출 버튼을 가린다.
            // 날짜 버튼으로 가는 경우는 남긴다 — 버튼을 누르는 동작이 다시 여닫기를 맡는다.
            if (next !== triggerRef.current) setOpen(false);
          }}
        />
      ) : null}
    </div>
  );
}

/**
 * 달력 팝오버. 날짜 버튼은 roving tabindex — Tab 한 번에 달력으로 들어오고, 화살표로 움직이고,
 * Enter·Space로 고르고, Esc로 닫는다(초점은 날짜 버튼으로 돌아간다).
 */
function CalendarPopover({
  id,
  label,
  selected,
  today,
  minDay,
  onPick,
  onClose,
  onFocusLeave,
}: {
  id: string;
  label: string;
  selected: Ymd | null;
  today: Ymd | null;
  minDay: Ymd | null;
  onPick: (day: Ymd) => void;
  onClose: () => void;
  /** 초점이 달력 밖 요소로 옮겨 갔다. 바깥 빈 곳 클릭(초점 대상 없음)은 pointerdown이 맡는다 */
  onFocusLeave: (next: Element) => void;
}) {
  const start = clampToSupported(selected ?? today ?? { year: SUPPORTED_YEARS.first, month: 1, day: 1 });
  const [focused, setFocused] = useState<Ymd>(start);
  const [view, setView] = useState({ year: start.year, month: start.month });
  const gridRef = useRef<HTMLDivElement>(null);

  /*
   * 초점을 옮길 날. 열릴 때(고른 날 또는 오늘)와 화살표를 눌렀을 때만 채운다 — 달 넘김
   * 버튼을 누를 때는 초점을 뺏지 않는다. 다음 프레임(rAF)에 미루면 빠르게 연달아 누를 때
   * 사라진 버튼에 초점이 남아 Enter가 허공에 떨어진다. 그래서 그린 직후 바로 옮긴다.
   */
  const focusTarget = useRef<string | null>(formatYmd(start));
  useLayoutEffect(() => {
    if (!focusTarget.current) return;
    gridRef.current?.querySelector<HTMLButtonElement>(`[data-day="${focusTarget.current}"]`)?.focus();
    focusTarget.current = null;
  }, [focused, view]);

  const canPrev =
    !(view.year === SUPPORTED_YEARS.first && view.month === 1) &&
    !(minDay && view.year === minDay.year && view.month <= minDay.month) &&
    !(minDay && view.year < minDay.year);
  const canNext = !(view.year === SUPPORTED_YEARS.last && view.month === 12);

  function shiftMonth(delta: number) {
    const next = addMonths(view, delta);
    setView(next);
    setFocused({ ...next, day: Math.min(focused.day, daysInMonth(next.year, next.month)) });
  }

  function onGridKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (!(event.key in step)) return;
    event.preventDefault();
    const next = clampToSupported(addDays(focused, step[event.key]));
    focusTarget.current = formatYmd(next);
    setFocused(next);
    setView({ year: next.year, month: next.month });
  }

  const leading = new Date(Date.UTC(view.year, view.month - 1, 1)).getUTCDay();
  const total = daysInMonth(view.year, view.month);
  const cells: (Ymd | null)[] = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: total }, (_, index) => ({ ...view, day: index + 1 })),
  ];

  const tomorrow = today ? addDays(today, 1) : null;

  return (
    <div
      id={id}
      role="dialog"
      aria-label={`${label} 날짜 고르기`}
      data-month={`${view.year}-${pad(view.month)}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}
      onBlur={(event) => {
        const next = event.relatedTarget;
        if (next instanceof Element && !event.currentTarget.contains(next)) onFocusLeave(next);
      }}
      className="motion-pop absolute top-full left-0 z-30 mt-2 w-full min-w-[300px] rounded-card border border-line bg-surface p-4 shadow-float sm:w-[340px]"
    >
      <div className="flex items-center justify-between">
        <p className="text-base font-bold" aria-live="polite">
          {view.year}년 {view.month}월
        </p>
        <div className="flex gap-1">
          <MonthButton label="이전 달" disabled={!canPrev} onClick={() => shiftMonth(-1)}>
            <ChevronLeftIcon className="size-5" />
          </MonthButton>
          <MonthButton label="다음 달" disabled={!canNext} onClick={() => shiftMonth(1)}>
            <ChevronRightIcon className="size-5" />
          </MonthButton>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-7 text-center text-sm font-bold" aria-hidden>
        {WEEKDAYS.map((weekday, index) => (
          <span
            key={weekday}
            className={`py-1 ${index === 0 ? "text-band-peak" : index === 6 ? "text-brand" : "text-ink-2"}`}
          >
            {weekday}
          </span>
        ))}
      </div>

      <div ref={gridRef} className="grid grid-cols-7 gap-y-1" onKeyDown={onGridKeyDown}>
        {cells.map((cell, index) => {
          if (!cell) return <span key={`blank-${index}`} aria-hidden />;
          const isSelected = selected !== null && sameDay(cell, selected);
          const isToday = today !== null && sameDay(cell, today);
          const isFocused = sameDay(cell, focused);
          const weekday = index % 7;
          // disabled 대신 aria-disabled: 막힌 날에도 화살표 초점이 머물 수 있어야 roving tabindex가 안 끊긴다.
          const isPast = minDay !== null && compareYmd(cell, minDay) < 0;
          return (
            <button
              key={cell.day}
              type="button"
              data-day={formatYmd(cell)}
              tabIndex={isFocused ? 0 : -1}
              aria-label={`${formatLong(cell)}${isToday ? ", 오늘" : ""}${isPast ? ", 지난 날짜" : ""}`}
              aria-pressed={isSelected}
              aria-disabled={isPast || undefined}
              onClick={() => {
                if (!isPast) onPick(cell);
              }}
              onFocus={() => setFocused(cell)}
              className={`tnum relative mx-auto flex size-10 items-center justify-center rounded-full text-[15px] font-bold transition-colors duration-150
                focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand
                ${
                  isSelected
                    ? "bg-brand text-white"
                    : isPast
                      ? "cursor-not-allowed text-ink-2 opacity-40"
                      : `hover:bg-brand-soft ${isToday ? "text-brand" : weekday === 0 ? "text-band-peak" : "text-ink"}`
                }`}
            >
              {cell.day}
              {isToday && !isSelected ? (
                <span className="absolute bottom-1 size-1 rounded-full bg-brand" aria-hidden />
              ) : null}
            </button>
          );
        })}
      </div>

      {today ? (
        <div className="mt-3 flex gap-2 border-t border-line pt-3">
          <QuickButton onClick={() => onPick(today)}>오늘</QuickButton>
          {tomorrow ? <QuickButton onClick={() => onPick(tomorrow)}>내일</QuickButton> : null}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto inline-flex min-h-11 items-center rounded-field px-3 text-sm font-bold text-ink-2 hover:bg-sunken"
          >
            닫기
          </button>
        </div>
      ) : null}
    </div>
  );
}

function MonthButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-11 place-items-center rounded-field text-ink-2 transition-colors duration-150 not-disabled:hover:bg-sunken not-disabled:hover:text-ink
        focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-35"
    >
      {children}
    </button>
  );
}

function QuickButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex min-h-11 items-center rounded-field border border-line px-4 text-sm font-bold text-ink transition-colors duration-150 hover:border-brand/50 hover:text-brand
        focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand"
    >
      {children}
    </button>
  );
}

function CalendarIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={className} aria-hidden>
      <rect x="3.5" y="5" width="17" height="15" rx="2.5" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" strokeLinecap="round" />
    </svg>
  );
}

function ChevronDownIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className={className} aria-hidden>
      <path d="M5.5 7.5 10 12l4.5-4.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── 날짜 계산 (전부 UTC 필드로 — 표준시가 끼어들 틈이 없다) ─────────────────────

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function parseYmd(value: string): Ymd | null {
  const matched = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!matched) return null;
  const [year, month, day] = matched.slice(1).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return { year, month, day };
}

function formatYmd({ year, month, day }: Ymd): string {
  return `${year}-${pad(month)}-${pad(day)}`;
}

function weekdayOf({ year, month, day }: Ymd): string {
  return WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
}

/** "11월 5일 (목)", 올해가 아니면 "2027년 1월 5일 (화)" */
function formatShort(ymd: Ymd, withYear = false): string {
  return `${withYear ? `${ymd.year}년 ` : ""}${ymd.month}월 ${ymd.day}일 (${weekdayOf(ymd)})`;
}

/** "2026년 11월 5일 목요일" — 스크린리더용 */
function formatLong(ymd: Ymd): string {
  return `${ymd.year}년 ${ymd.month}월 ${ymd.day}일 ${weekdayOf(ymd)}요일`;
}

function compareYmd(a: Ymd, b: Ymd): number {
  return Date.UTC(a.year, a.month - 1, a.day) - Date.UTC(b.year, b.month - 1, b.day);
}

function sameDay(a: Ymd, b: Ymd): boolean {
  return a.year === b.year && a.month === b.month && a.day === b.day;
}

function addDays(ymd: Ymd, delta: number): Ymd {
  const date = new Date(Date.UTC(ymd.year, ymd.month - 1, ymd.day + delta));
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() };
}

function addMonths(view: { year: number; month: number }, delta: number) {
  const date = new Date(Date.UTC(view.year, view.month - 1 + delta, 1));
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1 };
}

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function clampToSupported(ymd: Ymd): Ymd {
  if (ymd.year < SUPPORTED_YEARS.first) return { year: SUPPORTED_YEARS.first, month: 1, day: 1 };
  if (ymd.year > SUPPORTED_YEARS.last) return { year: SUPPORTED_YEARS.last, month: 12, day: 31 };
  return ymd;
}

/** 오늘·내일·모레만 이름을 붙인다. 그 밖은 날짜가 이미 말해 준다. */
function relativeLabel(day: string, today: string): string | null {
  const a = parseYmd(day);
  const b = parseYmd(today);
  if (!a || !b) return null;
  const diff = Math.round(
    (Date.UTC(a.year, a.month - 1, a.day) - Date.UTC(b.year, b.month - 1, b.day)) / 86_400_000,
  );
  return ({ 0: "오늘", 1: "내일", 2: "모레" } as Record<number, string>)[diff] ?? null;
}

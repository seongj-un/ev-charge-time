import type { ComponentProps, ReactNode } from "react";
import { useId } from "react";

const CONTROL =
  "w-full rounded-field bg-field border border-line px-3.5 h-12 text-ink " +
  "placeholder:text-ink-3 focus:outline-2 focus:outline-offset-0 focus:outline-brand " +
  "focus:border-brand transition-colors";

/** 라벨 + 입력 한 벌. 라벨과 입력의 id 연결을 매번 손으로 하지 않으려고 묶었다. */
export function Field({
  label,
  hint,
  suffix,
  error,
  className = "",
  ...props
}: ComponentProps<"input"> & {
  label: string;
  hint?: ReactNode;
  /** 입력 오른쪽에 붙는 단위 ("%", "kWh") */
  suffix?: string;
  error?: string;
}) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-bold text-ink-2 mb-2">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          className={`${CONTROL} tnum ${suffix ? "pr-10" : ""} ${
            error ? "border-danger outline-danger" : ""
          }`}
          {...props}
        />
        {suffix ? (
          <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-ink-3 pointer-events-none">
            {suffix}
          </span>
        ) : null}
      </div>
      {hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-ink-3">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** 라벨 + <select> 한 벌. 내 차량 고르기처럼 값이 정해진 곳에 쓴다. */
export function SelectField({
  label,
  hint,
  className = "",
  children,
  ...props
}: ComponentProps<"select"> & { label: string; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-bold text-ink-2 mb-2">
        {label}
      </label>
      <select id={id} className={`${CONTROL} appearance-none pr-10`} {...props}>
        {children}
      </select>
      {hint ? <p className="mt-1.5 text-xs text-ink-3">{hint}</p> : null}
    </div>
  );
}

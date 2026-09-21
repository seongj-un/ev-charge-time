"use client";

/**
 * 충전 방식 고르기. 라디오 버튼을 트랙 위 알약으로 보이게 한 것이라
 * 실제로도 라디오로 만든다 — 키보드 좌우 이동과 스크린리더가 공짜로 따라온다.
 */
export function SegmentedControl<T extends string>({
  name,
  label,
  value,
  options,
  onChange,
  className = "",
}: {
  name: string;
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <fieldset className={className}>
      <legend className="block text-sm font-bold text-ink-2 mb-2">{label}</legend>
      <div className="flex rounded-field bg-sunken p-1 gap-1">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <label
              key={option.value}
              className={`flex-1 cursor-pointer rounded-[9px] px-2 py-2.5 text-center text-sm font-bold transition-colors
                has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand
                ${selected ? "bg-surface text-ink shadow-sm" : "text-ink-3 hover:text-ink-2"}`}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                className="sr-only"
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

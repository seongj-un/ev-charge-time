/**
 * 셸에 쓰는 아이콘. 다섯 개뿐이라 아이콘 라이브러리를 들이지 않았다.
 * 전부 24×24 좌표계에 선 굵기 1.8로 맞춰 두면 나란히 놓았을 때 무게가 같다.
 */
type IconProps = { className?: string };

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function Svg({ className = "size-6", children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      {children}
    </svg>
  );
}

export const HomeIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <path d="M3.5 10.2 12 3.6l8.5 6.6V20a.9.9 0 0 1-.9.9h-4.4v-6h-6.4v6H4.4a.9.9 0 0 1-.9-.9z" {...stroke} />
  </Svg>
);

export const BoltIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <path d="M13.2 2.5 4.8 13.2h5.6l-.6 8.3 8.4-10.7h-5.6z" {...stroke} />
  </Svg>
);

export const ChartIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <path d="M4 20.2h16" {...stroke} />
    <path d="M6.6 17V9.4M11 17V4.6M15.4 17v-5.2M19.8 17v-8" {...stroke} />
  </Svg>
);

export const PinIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <path d="M12 21.2c3.9-4.2 5.9-7.4 5.9-9.8a5.9 5.9 0 0 0-11.8 0c0 2.4 2 5.6 5.9 9.8z" {...stroke} />
    <circle cx="12" cy="11.2" r="2.2" {...stroke} />
  </Svg>
);

export const PersonIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <circle cx="12" cy="8.2" r="3.6" {...stroke} />
    <path d="M4.8 20.4c.7-3.7 3.6-5.8 7.2-5.8s6.5 2.1 7.2 5.8" {...stroke} />
  </Svg>
);

export const ClockIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <circle cx="12" cy="12" r="8.6" {...stroke} />
    <path d="M12 7.2V12l3.2 2" {...stroke} />
  </Svg>
);

export const SunIcon = ({ className }: IconProps) => (
  <Svg className={className}>
    <circle cx="12" cy="12" r="4" {...stroke} />
    <path d="M12 2.8v2.4M12 18.8v2.4M4.6 4.6l1.7 1.7M17.7 17.7l1.7 1.7M2.8 12h2.4M18.8 12h2.4M4.6 19.4l1.7-1.7M17.7 6.3l1.7-1.7" {...stroke} />
  </Svg>
);

export const ChevronLeftIcon = ({ className = "size-5" }: IconProps) => (
  <Svg className={className}>
    <path d="M14.5 5.5 8 12l6.5 6.5" {...stroke} />
  </Svg>
);

export const ChevronRightIcon = ({ className = "size-5" }: IconProps) => (
  <Svg className={className}>
    <path d="M9.5 5.5 16 12l-6.5 6.5" {...stroke} />
  </Svg>
);

export const ArrowRightIcon = ({ className = "size-5" }: IconProps) => (
  <Svg className={className}>
    <path d="M4.5 12h15M13.5 6l6 6-6 6" {...stroke} />
  </Svg>
);

export const SaveIcon = ({ className = "size-5" }: IconProps) => (
  <Svg className={className}>
    <path d="M4.8 5.7A.9.9 0 0 1 5.7 4.8h9.5l4 4v9.5a.9.9 0 0 1-.9.9H5.7a.9.9 0 0 1-.9-.9z" {...stroke} />
    <path d="M8.4 4.8v4.4h6V4.8M8.4 19.2v-4.8h7.2v4.8" {...stroke} />
  </Svg>
);

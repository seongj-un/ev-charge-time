import Link from "next/link";
import type { ComponentType } from "react";

import { TodayPanel } from "@/components/home/TodayPanel";
import { ArrowRightIcon, BoltIcon, ChartIcon, ChatIcon, ClockIcon, PinIcon, SunIcon } from "@/components/shell/icons";
import { ButtonLink } from "@/components/ui/Button";
import { motionDelay } from "@/lib/motion";

/**
 * 홈.
 *
 * 머리: 질문 + 두 행동 + 오늘의 실제 요금 판(TodayPanel).
 * 본문: 화면 네 곳으로 가는 큰 타일 → 2026년 요금 개편 요점 → 출처.
 *
 * 홈은 추천 금액을 지어내지 않는다. 추천은 배터리 잔량·출발 시각 같은 조건이 있어야 나오고,
 * 조건 없이 금액을 보여주면 "내 차 기준"으로 읽힌다. 대신 조건 없이도 참인 '오늘의 시간대별
 * 단가'를 실데이터로 보여준다.
 */

type Tile = {
  href: string;
  title: string;
  body: string;
  icon: ComponentType<{ className?: string }>;
  note?: string;
};

const TILES: Tile[] = [
  {
    href: "/recommend",
    title: "충전 시간 추천",
    body: "배터리와 출발 시각만 넣으면 요금이 가장 싼 충전 구간을 찾아요.",
    icon: BoltIcon,
  },
  {
    href: "/ask",
    title: "질문하기",
    body: "\"내일 출근 전까지 80% 채우려면?\"처럼 말로 물어봐도 돼요.",
    icon: ChatIcon,
    note: "로그인 필요",
  },
  {
    href: "/timeline",
    title: "하루 단가",
    body: "날짜를 골라 시간대별 요금과 주말 할인 구간을 봐요.",
    icon: ChartIcon,
  },
  {
    href: "/stations",
    title: "주변 충전소",
    body: "가까운 충전기가 지금 비어 있는지 함께 확인해요.",
    icon: PinIcon,
  },
];

const FEATURES = [
  {
    icon: ClockIcon,
    // 겨울철 시간대는 개편 전후가 같다 (backend/config/tariff.yaml). 바뀐 건 봄·여름·가을이다.
    tag: "봄·여름·가을 평일",
    title: "바뀐 시간대",
    body: "평일 낮 11–15시는 중간요금으로 내려가고, 저녁 18–21시는 최고요금이 됐어요.",
    bar: "bg-band-peak",
  },
  {
    icon: SunIcon,
    tag: "봄·가을 주말",
    title: "낮 11–14시 절반",
    body: "토·일·공휴일 11–14시에는 전력량요금이 절반이에요. 언제 해당되는지 알려드려요.",
    bar: "bg-accent",
  },
  {
    icon: PinIcon,
    tag: "공공 데이터",
    title: "충전소 상태까지",
    body: "공공 데이터로 가까운 충전기의 사용 가능 여부를 함께 보여줘요.",
    bar: "bg-band-light",
  },
] as const;

export default function Home() {
  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto grid w-full max-w-[1280px] gap-8 px-5 py-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,500px)] lg:items-center lg:gap-16 lg:px-8 lg:py-16">
          <div className="motion-rise">
            <p className="inline-flex items-center gap-2 rounded-pill bg-brand-soft px-3 py-1.5 text-sm font-bold text-brand">
              <span className="size-2 rounded-full bg-brand" aria-hidden />
              <span className="lg:hidden">2026년 요금 개편 반영</span>
              <span className="hidden lg:inline">2026년 계절·시간대별 요금 개편 반영</span>
            </p>

            <h1 className="mt-5 text-display sm:text-[44px] lg:mt-6 lg:text-display-lg">
              <span className="block">언제 충전하면</span>{" "}
              <span className="block text-brand">가장 쌀까요?</span>
            </h1>

            <p className="mt-4 max-w-[40ch] text-base leading-relaxed text-ink-2 lg:mt-6 lg:text-lg">
              충전 조건만 넣으면 요금이 가장 싼 시간을 찾아드려요. 로그인 없이 바로 쓸 수 있어요.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row lg:mt-10">
              <ButtonLink href="/recommend" size="lg" className="w-full sm:w-auto">
                충전 시간 추천받기
                <ArrowRightIcon className="size-5" />
              </ButtonLink>
              <ButtonLink href="/timeline" variant="outline" size="lg" className="w-full sm:w-auto">
                오늘 단가 보기
              </ButtonLink>
            </div>
          </div>

          <div className="motion-rise" style={motionDelay(100)}>
            <TodayPanel />
          </div>
        </div>
      </section>

      <div className="mx-auto mt-6 w-full max-w-[1280px] px-5 sm:px-6 lg:mt-10 lg:px-8">
        <nav aria-label="바로가기" className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
          {TILES.map((tile, index) => (
            <HomeTile key={tile.href} tile={tile} delay={180 + index * 60} />
          ))}
        </nav>

        <section className="mt-12 lg:mt-16" aria-labelledby="changes-heading">
          <h2 id="changes-heading" className="text-[22px] font-bold tracking-tight lg:text-[26px]">
            2026년 요금 개편, 이것만 알면 돼요
          </h2>
          <div className="mt-6 grid gap-3 lg:mt-8 lg:grid-cols-3 lg:gap-4">
            {FEATURES.map(({ icon: Icon, tag, title, body, bar }, index) => (
              <article
                key={title}
                className="motion-rise overflow-hidden rounded-card border border-line bg-surface"
                style={motionDelay(420 + index * 60)}
              >
                <div className={`h-1.5 ${bar}`} aria-hidden />
                <div className="p-5 lg:p-6">
                  <div className="flex items-center gap-2 text-sm font-bold text-ink-2">
                    <Icon className="size-[18px] text-brand" />
                    {tag}
                  </div>
                  <h3 className="mt-3 text-section">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-2">{body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        {/*
          출처는 모바일에서도 남긴다. 요금이 "공식 확인 중"인 항목을 품고 있어서
          어디서 온 숫자인지 화면 어딘가에는 늘 적혀 있어야 한다.
        */}
        <footer className="mt-14 flex flex-col gap-1 border-t border-line pt-5 text-sm leading-relaxed text-ink-2 lg:mt-20 lg:flex-row lg:justify-between">
          <p>요금 정보: 기후에너지환경부·한전 발표 기준 · 일부 항목 공식 확인 중</p>
          <p>충전소 정보: 한국환경공단</p>
        </footer>
      </div>
    </>
  );
}

function HomeTile({ tile, delay }: { tile: Tile; delay: number }) {
  const Icon = tile.icon;
  return (
    <Link
      href={tile.href}
      style={motionDelay(delay)}
      // 마우스를 올리면 2px 떠오른다. 키보드 초점은 윤곽선이 맡는다.
      className="motion-rise group flex min-h-[156px] flex-col rounded-card border border-line bg-surface p-4 text-ink
        transition-[transform,border-color,box-shadow] duration-200 ease-out
        hover:-translate-y-0.5 hover:border-brand/50 hover:shadow-panel sm:p-5 lg:min-h-[180px] lg:p-6
        focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
    >
      <span className="grid size-10 place-items-center rounded-field bg-brand-soft text-brand" aria-hidden>
        <Icon className="size-5" />
      </span>
      <span className="mt-4 flex items-center gap-1 text-[17px] font-bold">
        {tile.title}
        <ArrowRightIcon className="size-4 text-ink-2 transition-colors duration-150 group-hover:text-brand" />
      </span>
      <span className="mt-1.5 text-sm leading-relaxed text-ink-2">{tile.body}</span>
      {tile.note ? <span className="mt-auto pt-3 text-sm font-bold text-ink-2">{tile.note}</span> : null}
    </Link>
  );
}

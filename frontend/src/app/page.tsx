import Link from "next/link";

import { PageContainer } from "@/components/shell/AppShell";
import { BoltIcon, ClockIcon, PinIcon, SunIcon } from "@/components/shell/icons";
import { SERVICE_NAME } from "@/components/shell/nav";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { formatSignedWon, formatWon } from "@/lib/format";

/**
 * 홈의 추천 카드는 API를 부르지 않는 고정값이다.
 *
 * 진짜 추천은 배터리 잔량·출발 시각 같은 조건이 있어야 나오는데 홈에는 그 입력이
 * 없다. 조건 없이 아무 값이나 불러다 놓으면 "내 차 기준 추천"으로 읽혀서 더
 * 나쁘다. 그래서 디자인대로 카드 라벨에 "예시"를 박아 두고 계산은 /recommend에서만
 * 한다.
 */
const EXAMPLE = {
  start: "22:00",
  end: "01:00",
  band: "경부하",
  savedWon: 399,
  condition: "평일 저녁 귀가 · 다음날 08시 출발",
} as const;

const FEATURES = [
  {
    icon: ClockIcon,
    title: "바뀐 시간대, 한눈에",
    body: "평일 낮 11–15시는 중간요금으로 내려가고, 저녁 18–21시는 최고요금이 됐어요.",
  },
  {
    icon: SunIcon,
    title: "봄·가을 주말 낮 할인",
    body: "토·일·공휴일 11–14시에는 전력량요금이 절반이에요. 언제 해당되는지 알려드려요.",
  },
  {
    icon: PinIcon,
    title: "주변 충전소 상태까지",
    body: "공공 데이터로 가까운 충전기의 사용 가능 여부를 함께 보여줘요.",
  },
] as const;

export default function Home() {
  return (
    <PageContainer className="pb-6 lg:pb-10">
      {/*
        데스크톱은 TopNav가 로고와 로그인을 이미 들고 있다. 같은 걸 두 번 그리면
        1024px 위에서 줄이 겹쳐 보이므로 모바일에서만 띄운다.
      */}
      <div className="flex items-center justify-between lg:hidden">
        <span className="flex items-center gap-2 font-bold text-ink">
          <BoltIcon className="size-5 text-brand" />
          {SERVICE_NAME}
        </span>
        <Link
          href="/login"
          className="inline-flex min-h-11 items-center text-sm font-bold text-ink underline underline-offset-4 hover:text-brand"
        >
          로그인
        </Link>
      </div>

      <section className="mt-10 lg:mt-16 lg:grid lg:grid-cols-2 lg:items-center lg:gap-16">
        <div>
          {/*
            긴 쪽은 390px에서 배지 폭을 넘긴다(Badge가 whitespace-nowrap이라 잘린다).
            한 문장에 조건부 span을 끼우는 대신 문구를 통째로 둘로 나눈 건, 토글되는
            span 경계의 공백이 붙었다 떨어졌다 하는 걸 피하려는 것이다.
          */}
          <Badge tone="off" className="px-3 py-1.5">
            <span className="lg:hidden">2026년 요금 개편 반영</span>
            <span className="hidden lg:inline">2026년 계절·시간대별 요금 개편 반영</span>
          </Badge>

          <h1 className="mt-4 text-display sm:text-[40px] lg:mt-6 lg:text-display-lg">
            <span className="block">언제 충전하면</span>{" "}
            <span className="block">가장 쌀까요?</span>
          </h1>

          <p className="mt-4 max-w-[40ch] text-base leading-relaxed text-ink-2 lg:mt-6">
            충전 조건만 넣으면 요금이 가장 싼 시간을 찾아드려요. 로그인 없이 바로 쓸 수 있어요.
          </p>

          <div className="mt-8 flex flex-col gap-3 lg:mt-10 lg:flex-row">
            <ButtonLink href="/recommend" size="lg" className="w-full lg:w-auto">
              충전 시간 추천받기
            </ButtonLink>
            {/*
              모바일에서는 아래 '하루 단가' 카드가 같은 곳으로 보내므로 숨긴다.
              버튼에 직접 hidden을 걸면 안 된다 — buttonClass가 이미 inline-flex를
              달고 있고 Tailwind 출력에서 .inline-flex가 .hidden보다 뒤에 와서
              모바일에서도 버튼이 그대로 보인다. 그래서 래퍼로 감춘다.
            */}
            <div className="hidden lg:block">
              <ButtonLink href="/timeline" variant="outline" size="lg">
                오늘 단가 보기
              </ButtonLink>
            </div>
          </div>
        </div>

        <div className="mt-6 lg:mt-0">
          <Card tone="ink" className="p-5 lg:p-7">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-bold text-white/80">추천 충전 시간 · 예시</p>
              <Badge tone="ok">{EXAMPLE.band}</Badge>
            </div>

            <p className="tnum mt-3 text-[30px] font-bold tracking-tight lg:mt-4 lg:text-[40px]">
              {EXAMPLE.start} – {EXAMPLE.end}
            </p>

            {/* 모바일은 라임 카드 자리가 없어 절감액을 카드 안에 한 줄로 넣는다 */}
            <p className="mt-3 text-sm text-white/80 lg:hidden">
              바로 충전할 때보다 <span className="tnum">{formatWon(EXAMPLE.savedWon)}</span> 절약
            </p>
            <p className="mt-4 hidden text-sm text-white/80 lg:block">{EXAMPLE.condition}</p>
          </Card>

          <Card tone="accent" className="mt-3 hidden items-center justify-between p-5 lg:flex">
            <span className="text-sm font-bold">바로 충전할 때보다</span>
            <span className="tnum text-2xl font-bold">{formatSignedWon(EXAMPLE.savedWon)}</span>
          </Card>
        </div>
      </section>

      {/* 모바일 전용 바로가기. 데스크톱에서는 상단 버튼과 아래 특징 카드가 대신한다. */}
      <section className="mt-6 grid grid-cols-2 gap-3 lg:hidden">
        <HomeShortcut
          href="/timeline"
          title="하루 단가"
          body="시간대별 요금과 주말 할인 구간"
        />
        <HomeShortcut href="/stations" title="주변 충전소" body="가까운 충전기 사용 가능 여부" />
      </section>

      <section className="mt-20 hidden gap-x-12 lg:grid lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <div key={title} className="border-t border-line pt-6">
            <Icon className="size-5 text-brand" />
            <h2 className="mt-4 text-lg font-bold">{title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-2">{body}</p>
          </div>
        ))}
      </section>

      {/*
        출처는 모바일에서도 남긴다. 요금이 "공식 확인 중"인 항목을 품고 있어서
        어디서 온 숫자인지 화면 어딘가에는 늘 적혀 있어야 한다.
      */}
      <footer className="mt-10 flex flex-col gap-1 border-t border-line pt-5 text-sm leading-relaxed text-ink-2 lg:mt-24 lg:flex-row lg:justify-between lg:border-0 lg:pt-0">
        <p>요금 정보: 기후에너지환경부·한전 발표 기준 · 일부 항목 공식 확인 중</p>
        <p>충전소 정보: 한국환경공단</p>
      </footer>
    </PageContainer>
  );
}

function HomeShortcut({ href, title, body }: { href: string; title: string; body: string }) {
  return (
    <Link
      href={href}
      className="rounded-card border border-line bg-surface p-4 transition-colors duration-150 hover:border-ink-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
    >
      <h2 className="text-base font-bold">{title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{body}</p>
    </Link>
  );
}

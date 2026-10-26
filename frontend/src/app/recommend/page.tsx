import type { Metadata } from "next";

import type { Mode } from "@/lib/api/types";
import { fromSearchParams, type RecommendForm } from "@/lib/recommend-params";

import { ChargeForm } from "@/components/recommend/ChargeForm";
import { PageContainer } from "@/components/shell/AppShell";
import { BoltIcon } from "@/components/shell/icons";
import { SERVICE_NAME } from "@/components/shell/nav";
import { Card } from "@/components/ui/Card";

export const metadata: Metadata = {
  title: "충전 시간 추천",
  description:
    "배터리 용량과 충전기 출력, 원하는 충전량과 시간대를 넣으면 가장 싼 충전 시각을 찾아드립니다.",
};

/** 데스크톱 시안(p-15)의 오른쪽 안내 카드. 모바일 시안에는 없어서 lg에서만 띄운다. */
const GUIDES = [
  {
    title: "이렇게 찾아요",
    body: "시작 가능 시각부터 완료 시각 사이에서, 계절·요일·시간대 요금과 주말 할인을 따져 가장 싼 구간을 골라요.",
  },
  {
    title: "계산 가정",
    body: "충전 출력은 일정하고, 한 번에 이어서 충전한다고 봐요. 기본요금은 빼고 계산해요.",
  },
];

const MODES: Mode[] = ["self_low", "self_high", "public_fast"];

/**
 * 이 화면으로 들어오는 쿼리는 두 갈래다.
 *
 * - 결과 화면의 "조건 고치기"는 조건 전체(battery_kwh·…·mode)를 달고 온다. 그걸 다
 *   읽어 폼을 채운다 — 예전에는 day·mode만 읽어서 돌아오는 순간 넣었던 값이 날아갔다.
 * - 하루 단가 화면의 "이 날짜로 추천받기"는 ?day=·?mode=(·?public_base_price=)를 단다.
 *
 * 서버에서 읽어 폼에 내려준다 — useSearchParams를 쓰면 이 화면이 동적이 되고
 * Suspense 경계가 필요해지는데, 쿼리 몇 개 읽자고 그럴 이유가 없다.
 */
export default async function RecommendPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const read = (key: string) => (typeof params[key] === "string" ? params[key] : null);

  // 조건이 통째로 왔으면 그게 우선이다. 하나라도 모양이 안 맞으면 null이라 아래로 간다.
  const initialForm = fromSearchParams({ get: read });

  const day = read("day") ?? undefined;
  const rawMode = read("mode");
  const mode = MODES.includes(rawMode as Mode) ? (rawMode as Mode) : undefined;
  // 하루 단가에서 공용 급속으로 넘어오면 거기서 넣은 단가도 따라온다.
  const rawPrice = Number(read("public_base_price"));
  const price = mode === "public_fast" && rawPrice > 0 && Number.isFinite(rawPrice) ? rawPrice : undefined;

  return renderPage(day, mode, initialForm, price);
}

function renderPage(
  initialDay?: string,
  initialMode?: Mode,
  initialForm?: RecommendForm | null,
  initialPrice?: number,
) {
  return (
    <PageContainer className="pb-6">
      {/* 모바일에는 상단 내비가 없다(탭바가 대신한다). 그래서 로고를 화면이 직접 단다. */}
      <p className="flex items-center gap-2 text-sm font-bold text-ink lg:hidden">
        <BoltIcon className="size-5 text-brand" />
        {SERVICE_NAME}
      </p>

      {/*
       * 데스크톱에서는 카드 제목 "충전 조건 입력"이 눈에 보이는 머리글이지만,
       * 화면 전체의 이름은 여전히 이 문장이다. 지우지 않고 sr-only로 남겨
       * 어느 폭에서든 h1이 하나씩 있게 한다.
       */}
      <h1 className="mt-3 text-[28px] font-bold leading-[1.25] tracking-tight lg:sr-only lg:mt-0">
        언제 충전하면
        <br />
        가장 쌀까요?
      </h1>

      <div className="mt-6 lg:mt-0 lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-8">
        <ChargeForm
          initialDay={initialDay}
          initialMode={initialMode}
          initialForm={initialForm}
          initialPrice={initialPrice}
        />

        <aside className="hidden lg:flex lg:flex-col lg:gap-4">
          {GUIDES.map((guide) => (
            <Card key={guide.title} tone="sunken" className="p-5">
              <h2 className="text-sm font-bold text-ink">{guide.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{guide.body}</p>
            </Card>
          ))}
        </aside>
      </div>
    </PageContainer>
  );
}

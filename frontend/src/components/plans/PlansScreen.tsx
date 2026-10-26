"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { MeLayout } from "@/components/me/MeSidebar";
import { ChevronLeftIcon } from "@/components/shell/icons";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { deletePlan, fetchPlanSummary } from "@/lib/api/endpoints";
import type { PlanSummary, SavedPlan } from "@/lib/api/types";
import { formatWon } from "@/lib/format";

import { useIsHydrated } from "./hooks";
import { loadPlanPage } from "./load-plans";
import { currentMonth, formatMonth, isMonth, monthOptions } from "./plan-view";
import { PlanRecordList } from "./PlanRecordList";

/**
 * 충전 기록 (/me/plans, F-13).
 *
 * 세 가지를 조심해서 만들었다.
 *
 * 1) 고른 달은 URL이 정본이다. 컴포넌트 state에만 두면 새로고침하면 이번 달로
 *    돌아가고 "9월 절감액 이렇게 나왔어" 링크를 보낼 수가 없다.
 *
 * 2) 이번 달은 브라우저에 붙은 다음에만 계산한다. 서버는 UTC, 사용자는 KST라
 *    월말 밤에는 서버와 브라우저가 서로 다른 달을 그린다 (hooks.ts).
 *
 * 3) 목록 API에는 아직 달 필터가 없다. 화면에서 거르되(load-plans.ts), 그 때문에
 *    생기는 "다음 페이지에 있는 그 달 기록"을 숨기지 않고 숫자로 말한다.
 */

type ListState = {
  items: SavedPlan[];
  nextCursor: string | null;
  loading: boolean;
  /** 더 보기 진행 중 표시도 목록과 한 묶음이다 — 달이 바뀌어 목록을 비우면 같이 꺼진다. */
  loadingMore: boolean;
  error: string | null;
};

const EMPTY_LIST: ListState = {
  items: [],
  nextCursor: null,
  loading: true,
  loadingMore: false,
  error: null,
};

export function PlansScreen() {
  const hydrated = useIsHydrated();
  const { status } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const query = searchParams.toString();
  const monthParam = searchParams.get("month");
  // hydration 전에는 '이번 달'을 모른다 — 서버와 같은 화면(불러오는 중)을 그린다.
  const month = isMonth(monthParam) ? monthParam : hydrated ? currentMonth(new Date()) : null;

  const [reloadKey, setReloadKey] = useState(0);
  const [list, setList] = useState<ListState>(EMPTY_LIST);
  /**
   * 지금 화면에 깔린 목록의 세대 번호. 첫 페이지를 새로 부를 때마다(달 변경, 다시 시도)
   * 하나 올린다. 더 보기는 떠날 때의 번호를 쥐고 가서, 돌아왔을 때 번호가 바뀌었으면
   * 아무것도 건드리지 않는다. 달만 비교하면 10월→9월→10월로 돌아온 뒤 도착한
   * 첫 번째 10월 요청의 응답이 새 10월 목록에 붙는다 — 그래서 달이 아니라 세대를 본다.
   */
  const generationRef = useRef(0);
  const [summary, setSummary] = useState<PlanSummary | null>(null);

  /**
   * 요약은 응답에 month가 실려 온다. 그 값이 지금 보고 있는 달과 같을 때만 쓰면
   * 늦게 도착한 옛 달의 요약이 새 달 카드에 얹히는 일이 없다.
   */
  const monthSummary = summary?.month === month ? summary : null;

  const refreshSummary = useCallback(async (target: string) => {
    try {
      setSummary(await fetchPlanSummary(target));
    } catch {
      // 요약은 있으면 좋은 것이다. 못 받았다고 목록까지 막지 않는다.
      setSummary(null);
    }
  }, []);

  useEffect(() => {
    if (status !== "authenticated" || month === null) return;

    let cancelled = false;
    generationRef.current += 1;
    setList(EMPTY_LIST);

    void (async () => {
      try {
        const page = await loadPlanPage({ month });
        if (cancelled) return;
        setList({
          items: page.items,
          nextCursor: page.nextCursor,
          loading: false,
          loadingMore: false,
          error: null,
        });
      } catch (caught) {
        if (cancelled) return;
        setList({ ...EMPTY_LIST, loading: false, error: messageOf(caught) });
      }
    })();

    void refreshSummary(month);

    return () => {
      cancelled = true;
    };
  }, [status, month, reloadKey, refreshSummary]);

  const handleMonthChange = useCallback(
    (next: string) => {
      const params = new URLSearchParams(query);
      params.set("month", next);
      // 달을 훑어볼 때마다 히스토리가 쌓이면 뒤로 가기로 이 화면을 못 벗어난다.
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, query, router],
  );

  /*
   * 더 보기는 누른 순간의 목록에 속한 요청이다. 기다리는 사이 달을 바꾸면 그 응답은
   * 새 달 목록과 상관이 없다 — 붙이면 9월 목록에 10월 기록이 섞이고, 그 응답의 커서가
   * 9월 더 보기를 10월 다음 페이지로 보낸다. 그래서 결과도, 실패도, 진행 중 표시를
   * 끄는 것도 세대가 그대로일 때만 한다.
   */
  const loadMore = useCallback(async () => {
    const cursor = list.nextCursor;
    if (month === null || cursor === null || list.loadingMore) return;
    const generation = generationRef.current;
    const isCurrent = () => generationRef.current === generation;
    setList((prev) => ({ ...prev, loadingMore: true }));
    try {
      const page = await loadPlanPage({ month, cursor });
      if (!isCurrent()) return;
      setList((prev) => ({
        ...prev,
        items: [...prev.items, ...page.items],
        nextCursor: page.nextCursor,
        loadingMore: false,
      }));
    } catch (caught) {
      if (!isCurrent()) return;
      setList((prev) => ({ ...prev, loadingMore: false, error: messageOf(caught) }));
    }
  }, [list.nextCursor, list.loadingMore, month]);

  const handleDelete = useCallback(
    async (id: string) => {
      await deletePlan(id); // 실패하면 그대로 던진다 — 줄이 사유를 자기 자리에 띄운다.
      setList((prev) => ({ ...prev, items: prev.items.filter((item) => item.id !== id) }));
      // 건수와 절감 합계는 서버가 센다. 화면에서 빼면 서버 값과 어긋난다.
      if (month !== null) void refreshSummary(month);
    },
    [month, refreshSummary],
  );

  const backTo = query === "" ? pathname : `${pathname}?${query}`;

  return (
    /* 마이페이지 공통 뼈대(데스크톱 좌측 메뉴 + 본문). 요약·내 차량 화면과 같은 것을 쓴다 —
       화면마다 사이드바를 따로 그리면 메뉴를 옮겨 다닐 때 좌측이 흔들린다. */
    <MeLayout>
      <div className="flex items-center gap-2">
        {/* 모바일에는 사이드바가 없다. 마이페이지로 돌아갈 길을 제목 옆에 둔다. */}
        <Link
          href="/me"
          aria-label="마이페이지로"
          className="-ml-1 rounded-pill p-1 text-ink-2 transition-colors hover:text-ink
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand lg:hidden"
        >
          <ChevronLeftIcon className="size-5" />
        </Link>

        <h1 className="text-xl font-bold lg:text-[26px]">충전 기록</h1>

        {status === "authenticated" && month !== null ? (
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-sm text-ink-2 lg:inline" aria-hidden>
              월
            </span>
            <MonthSelect month={month} onChange={handleMonthChange} />
          </div>
        ) : null}
      </div>

      {!hydrated || status === "loading" ? (
        <p role="status" className="mt-6 text-sm text-ink-3">
          충전 기록을 불러오고 있어요…
        </p>
      ) : null}

      {status === "unreachable" ? (
        <Notice className="mt-5">
          서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하세요. 로그인 여부를 확인하지
          못해 기록을 불러오지 않았습니다.
        </Notice>
      ) : null}

      {status === "anonymous" ? (
        <Card className="mt-5 p-6 lg:mt-6 lg:p-8">
          <h2 className="text-lg font-bold">로그인이 필요해요</h2>
          <p className="mt-2 max-w-[32rem] text-sm leading-relaxed text-ink-2">
            충전 기록은 계정에 저장됩니다. 로그인하면 저장한 계획과 달별 절감액을 볼 수 있어요.
            추천 자체는 로그인 없이도 그대로 쓸 수 있습니다.
          </p>
          <div className="mt-6 flex flex-wrap gap-2.5">
            {/* 돌아올 곳을 달고 보낸다 — 로그인 뒤 보던 달로 그대로 돌아온다. */}
            <ButtonLink href={`/login?next=${encodeURIComponent(backTo)}`} size="lg">
              로그인하기
            </ButtonLink>
            <ButtonLink href="/recommend" variant="outline" size="lg">
              충전 시간 추천받기
            </ButtonLink>
          </div>
        </Card>
      ) : null}

      {status === "authenticated" && month !== null ? (
        <>
          <SummaryCards summary={monthSummary} />

          {list.loading ? (
            <div role="status" className="mt-4 space-y-3 lg:mt-5">
              <p className="text-sm text-ink-3">기록을 불러오고 있어요…</p>
              <div className="h-[92px] animate-pulse rounded-card bg-sunken" />
              <div className="h-[92px] animate-pulse rounded-card bg-sunken" />
            </div>
          ) : null}

          {list.error ? (
            <Card className="mt-4 p-6 lg:mt-5">
              <h2 className="text-base font-bold">기록을 불러오지 못했어요</h2>
              <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-2">
                {list.error}
              </p>
              <Button
                type="button"
                variant="outline"
                className="mt-5"
                onClick={() => setReloadKey((value) => value + 1)}
              >
                다시 시도
              </Button>
            </Card>
          ) : null}

          {!list.loading && !list.error ? (
            <PlansBody
              month={month}
              list={list}
              summary={monthSummary}
              onLoadMore={() => void loadMore()}
              onDelete={handleDelete}
            />
          ) : null}
        </>
      ) : null}

      <Footnote items={list.items} />
    </MeLayout>
  );
}

function PlansBody({
  month,
  list,
  summary,
  onLoadMore,
  onDelete,
}: {
  month: string;
  list: ListState;
  summary: PlanSummary | null;
  onLoadMore: () => void;
  onDelete: (id: string) => Promise<void>;
}) {
  const shortfall = shortfallMessage({
    month,
    shown: list.items.length,
    total: summary?.count ?? null,
    hasMore: list.nextCursor !== null,
  });

  if (list.items.length === 0 && shortfall === null) {
    return (
      /*
       * 달을 특정해서 말한다. 월 기준이 충전 날짜라, 9월에 세운 10월 계획은
       * 9월 목록에 없다 — 그건 맞다. 그런데 "아직 저장한 계획이 없어요"라고 하면
       * 거짓말이 된다. 계획은 있고, 다른 달에 있을 뿐이다.
       */
      <Card className="mt-4 p-6 text-center lg:mt-5 lg:p-10">
        <h2 className="text-base font-bold">{formatMonth(month)}에 충전할 계획이 없어요</h2>
        <p className="mx-auto mt-2 max-w-[28rem] text-sm leading-relaxed text-ink-2">
          다른 달에 저장한 계획이 있을 수 있어요. 위에서 달을 바꿔 보세요. 추천 결과
          화면에서 &lsquo;충전 기록에 저장&rsquo;을 누르면 여기에 쌓입니다.
        </p>
        <ButtonLink href="/recommend" size="lg" className="mt-6">
          충전 시간 추천받기
        </ButtonLink>
      </Card>
    );
  }

  return (
    <>
      {shortfall ? (
        <Notice className="mt-4 lg:mt-5">{shortfall}</Notice>
      ) : null}

      {list.items.length > 0 ? (
        <PlanRecordList items={list.items} onDelete={onDelete} />
      ) : null}

      {list.nextCursor !== null ? (
        <div className="mt-4 flex justify-center">
          <Button type="button" variant="outline" disabled={list.loadingMore} onClick={onLoadMore}>
            {list.loadingMore ? "불러오는 중…" : "더 보기"}
          </Button>
        </div>
      ) : null}
    </>
  );
}

/**
 * 아직 안 불러온 기록이 남았는지 한 줄로 말한다.
 *
 * 이제 필터도 정렬도 서버가 충전 날짜 기준으로 한다. 그래서 "그 달 기록이 다음
 * 페이지에 숨어 있다"는 예전 구멍은 없다 — 남은 건 순수한 페이지네이션뿐이다.
 * 그래도 요약 건수와 화면 건수를 맞대 두면, 사용자가 "이게 전부인가"를 묻지 않아도 된다.
 */
export function shortfallMessage(params: {
  month: string;
  shown: number;
  total: number | null;
  hasMore: boolean;
}): string | null {
  const { month, shown, total, hasMore } = params;
  const label = formatMonth(month);

  if (total !== null && total > shown) {
    return `${label} 기록 ${total}건 중 ${shown}건을 불러왔어요. 나머지는 ‘더 보기’로 불러오면 보입니다.`;
  }

  if (hasMore) {
    return `아직 불러오지 않은 기록이 남아 있어요.`;
  }

  return null;
}

function SummaryCards({ summary }: { summary: PlanSummary | null }) {
  return (
    <div className="mt-5 grid grid-cols-2 gap-3 lg:mt-6 lg:gap-5">
      <Card className="p-4 lg:p-6">
        <p className="text-xs font-bold text-ink-2 lg:text-sm">저장한 계획</p>
        <p className="mt-1 text-2xl font-bold lg:mt-2 lg:text-[32px]">
          {summary ? (
            <>
              <span className="tnum">{summary.count}</span>건
            </>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </p>
      </Card>

      <Card tone="accent" className="p-4 lg:p-6">
        <p className="text-xs font-bold lg:text-sm">예상 절감 합계</p>
        <p className="mt-1 text-2xl font-bold lg:mt-2 lg:text-[32px]">
          {summary ? (
            <span className="tnum">{formatWon(summary.total_savings_won)}</span>
          ) : (
            <span className="opacity-50">—</span>
          )}
        </p>
      </Card>
    </div>
  );
}

/**
 * 각주.
 *
 * 디자인 시안의 마지막 문장은 "표시된 값은 예시예요"였다. 자리표시자 숫자를 쓰던
 * 시안에서는 맞는 말이지만, 지금은 저장된 진짜 값을 보여주므로 그대로 적으면
 * 거짓말이 된다. 대신 실제로 조심해야 하는 것 — 저장 당시 요금표로 계산한 값이라
 * 지금 다시 계산하면 달라진다는 것 — 을 적는다.
 */
function Footnote({ items }: { items: SavedPlan[] }) {
  const versions = Array.from(new Set(items.map((item) => item.tariff_version)));
  const version = versions.length === 1 ? versions[0] : null;

  return (
    <p className="mt-8 text-xs leading-relaxed text-ink-3 lg:mt-10">
      저장한 계획이며 실제 충전 기록이 아니에요. 금액은 저장 당시 요금표
      {version ? <span className="tnum">({version})</span> : null} 기준이라, 지금 다시
      계산하면 달라질 수 있어요.
    </p>
  );
}

function MonthSelect({
  month,
  onChange,
}: {
  month: string;
  onChange: (next: string) => void;
}) {
  const options = monthOptions(new Date(), month);

  return (
    <select
      aria-label="월 선택"
      value={month}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 rounded-field border border-line bg-surface px-3 text-sm font-bold text-ink
        focus:outline-2 focus:outline-offset-0 focus:outline-brand"
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {formatMonth(option)}
        </option>
      ))}
    </select>
  );
}

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "충전 기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

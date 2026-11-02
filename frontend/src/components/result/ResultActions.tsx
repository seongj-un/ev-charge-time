"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { SaveIcon } from "@/components/shell/icons";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { savePlan } from "@/lib/api/endpoints";
import type { SavedPlan } from "@/lib/api/types";
import { formatSignedWon, formatWon } from "@/lib/format";
import { fromSearchParams, toSavePlanRequest } from "@/lib/recommend-params";

/**
 * 화면 아래 행동들.
 *
 * 모바일은 버튼 세 개, 데스크톱은 안내 카드 두 장이다. 버튼 자체는 한 벌만 두고
 * 감싸는 껍데기와 글자만 바꾼다 — 같은 버튼이 DOM에 두 개 있으면 "어느 저장 버튼을
 * 눌렀는지"에 따라 다르게 도는 코드가 언젠가 생긴다.
 */
export function ResultActions() {
  return (
    <div className="mt-6 grid grid-cols-2 gap-3 lg:mt-8 lg:gap-5">
      <SavePlanAction />

      {/* 하루 단가는 데스크톱에선 상단 내비에 이미 있다. */}
      <ButtonLink
        href="/timeline"
        variant="outline"
        size="lg"
        className="w-full text-sm lg:hidden"
      >
        하루 단가 보기
      </ButtonLink>

      <div className="lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-6">
        <div className="lg:flex lg:items-center lg:justify-between lg:gap-4">
          <div className="hidden lg:block">
            <h2 className="text-lg font-bold">어디서 충전할까요?</h2>
            <p className="mt-1 text-sm text-ink-2">가까운 충전소와 충전기 상태를 확인하세요.</p>
          </div>
          <ButtonLink
            href="/stations"
            variant="outline"
            size="lg"
            className="w-full text-sm lg:h-12 lg:w-auto lg:shrink-0 lg:border-transparent lg:bg-brand lg:text-white lg:hover:bg-ink"
          >
            주변 충전소
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}

type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; plan: SavedPlan }
  | { status: "error"; message: string; needsLogin: boolean };

/**
 * "충전 기록에 저장" (POST /api/me/plans, F-13).
 *
 * 저장할 조건은 주소에서 읽는다. ResultView가 이미 같은 조건을 들고 있지만 이 컴포넌트에
 * 내려주지 않고, ResultView는 이번 작업에서 건드리지 않기로 한 파일이다. 어차피 조건의
 * 정본은 URL이라(recommend-params.ts) 읽는 곳이 하나 늘어도 값이 갈라질 일은 없다.
 *
 * ⚠️ 서버는 받은 조건으로 **다시 계산해서** 저장한다. 그래서 저장 뒤 보여주는 금액은
 * 화면에 떠 있던 값이 아니라 응답의 result다 — 둘이 다르면 맞는 쪽은 서버다.
 */
function SavePlanAction() {
  const { status } = useSession();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.toString();

  // 조건이 반쪽이면 요청을 보내지 않는다. 422를 받아 오류를 띄우는 건 낭비다.
  const form = useMemo(() => fromSearchParams(new URLSearchParams(query)), [query]);

  const [state, setState] = useState<SaveState>({ status: "idle" });

  // 로그인 뒤 이 화면으로 그대로 돌아와야 한다 — 조건이 주소에 다 들어 있다.
  const resultUrl = query === "" ? pathname : `${pathname}?${query}`;
  const loginHref = `/login?next=${encodeURIComponent(resultUrl)}`;

  // 세션이 만료된 채 눌렀을 수도 있다. 그때도 "실패했습니다"로 끝내지 않고 길을 준다.
  const needsLogin =
    status === "anonymous" || (state.status === "error" && state.needsLogin);

  async function save() {
    // 같은 계획이 두 번 저장되면 기록이 중복되고 달별 절감 합계가 부풀려진다.
    if (form === null || state.status === "saving" || state.status === "saved") return;

    setState({ status: "saving" });
    try {
      setState({ status: "saved", plan: await savePlan(toSavePlanRequest(form)) });
    } catch (caught) {
      const apiError = caught instanceof ApiError ? caught : null;
      setState({
        status: "error",
        message: apiError?.message ?? "저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        needsLogin: apiError?.needsLogin ?? false,
      });
    }
  }

  const description = needsLogin
    ? "로그인하면 충전 기록에 쌓이고 달별 절감액을 볼 수 있어요."
    : "저장해 두면 달별 절감액을 모아 볼 수 있어요.";

  // 로그인 안내는 모바일에서도 보여야 한다 — 버튼이 왜 "로그인하고 저장"인지
  // 설명 없이 로그인 화면으로 보내면 안 된다. 그 밖에는 시안대로 데스크톱에만 둔다.
  const descriptionOnDesktopOnly = !needsLogin && state.status !== "saved";

  return (
    <div className="col-span-2 lg:col-span-1 lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-6">
      <div className="lg:flex lg:items-center lg:justify-between lg:gap-4">
        <div className="lg:min-w-0">
          <h2 className="hidden text-lg font-bold lg:block">이 계획을 저장할까요?</h2>
          <p
            className={`mb-2.5 text-sm text-ink-2 lg:mt-1 lg:mb-0 ${
              descriptionOnDesktopOnly ? "hidden lg:block" : ""
            }`}
          >
            {description}
          </p>
        </div>

        {/* 저장이 끝나면 버튼을 치운다 — 남겨 두면 한 번 더 눌러 기록이 중복된다. */}
        {state.status === "saved" ? null : needsLogin ? (
          <ButtonLink
            href={loginHref}
            size="lg"
            className="w-full text-sm lg:h-12 lg:w-auto lg:shrink-0 lg:bg-ink lg:hover:bg-ink/90"
          >
            <SaveIcon className="size-5 lg:hidden" />
            로그인하고 저장
          </ButtonLink>
        ) : (
          <Button
            type="button"
            size="lg"
            onClick={() => void save()}
            disabled={form === null || status === "loading" || state.status === "saving"}
            className="w-full text-sm lg:h-12 lg:w-auto lg:shrink-0 lg:bg-ink lg:hover:bg-ink/90"
          >
            <SaveIcon className="size-5 lg:hidden" />
            충전 기록에 저장
          </Button>
        )}
      </div>

      {form === null ? (
        <p className="mt-2.5 text-sm text-ink-2">
          주소에 충전 조건이 들어 있지 않아 저장할 수 없어요.
        </p>
      ) : null}

      {state.status === "saved" ? (
        <div
          role="status"
          className="mt-3 rounded-field bg-ok-bg px-3.5 py-3 text-sm text-ok-fg lg:mt-4"
        >
          <p className="font-bold">충전 기록에 저장했어요</p>
          {/*
            서버가 저장 시점에 다시 계산한다. 화면에 떠 있던 금액을 그대로 옮겨 적으면
            기록 목록에 들어간 값과 다른 숫자를 보여주게 된다.
          */}
          <p className="mt-1">
            저장된 값은 예상{" "}
            <span className="tnum">{formatWon(state.plan.result.best.cost_won)}</span> ·{" "}
            <span className="tnum">{formatSignedWon(state.plan.result.savings_won)}</span>{" "}
            입니다.
          </p>
          <ButtonLink href="/me/plans" variant="outline" className="mt-3">
            충전 기록 보기
          </ButtonLink>
        </div>
      ) : null}

      {state.status === "error" ? (
        <div role="alert" className="mt-3 lg:mt-4">
          <Notice>
            <strong className="font-bold">저장하지 못했어요</strong> · {state.message}
          </Notice>
        </div>
      ) : null}
    </div>
  );
}

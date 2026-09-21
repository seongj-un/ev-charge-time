"use client";

import { useState } from "react";

import { SaveIcon } from "@/components/shell/icons";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";

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
            <h2 className="text-base font-bold">어디서 충전할까요?</h2>
            <p className="mt-1 text-sm text-ink-2">가까운 충전소와 충전기 상태를 확인하세요.</p>
          </div>
          <ButtonLink
            href="/stations"
            variant="outline"
            size="lg"
            className="w-full text-sm lg:h-11 lg:w-auto lg:shrink-0 lg:border-transparent lg:bg-brand lg:text-white lg:hover:bg-brand/90"
          >
            주변 충전소
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}

/**
 * "충전 기록에 저장".
 *
 * 백엔드 `/api/me/plans`는 아직 501이고 로그인도 없다. 그래서 눌렀을 때
 * 저장된 척하지 않는다 — 버튼을 없애면 이 화면에 저장이 있을 예정이라는 사실이
 * 사라지고, 성공 토스트를 띄우면 없는 기능을 있다고 말하는 게 된다.
 * 대신 왜 아직 안 되는지와, 지금 당장 할 수 있는 대안(주소 저장)을 알려준다.
 */
function SavePlanAction() {
  const [explained, setExplained] = useState(false);

  return (
    <div className="col-span-2 lg:col-span-1 lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-6">
      <div className="lg:flex lg:items-center lg:justify-between lg:gap-4">
        <div className="hidden lg:block">
          <h2 className="text-base font-bold">이 계획을 저장할까요?</h2>
          <p className="mt-1 text-sm text-ink-2">
            로그인하면 충전 기록에 쌓이고 달별 절감액을 볼 수 있어요.
          </p>
        </div>
        <Button
          type="button"
          size="lg"
          onClick={() => setExplained(true)}
          className="w-full text-sm lg:h-11 lg:w-auto lg:shrink-0 lg:bg-ink lg:hover:bg-ink/90"
        >
          <SaveIcon className="size-5 lg:hidden" />
          <span className="lg:hidden">충전 기록에 저장</span>
          <span className="hidden lg:inline">로그인하고 저장</span>
        </Button>
      </div>

      {explained ? (
        <div role="alert" className="mt-3 lg:mt-4">
          <Notice>
            <strong className="font-bold">로그인 기능 준비 중</strong>이라 아직 저장할 수
            없습니다. 이 화면의 주소에 조건이 들어 있으니, 주소를 저장해 두면 같은 추천을
            그대로 다시 열 수 있어요.
          </Notice>
        </div>
      ) : null}
    </div>
  );
}

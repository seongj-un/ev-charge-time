import type { ReactNode } from "react";

import { Badge } from "./Badge";
import { ButtonLink } from "./Button";
import { Notice } from "./Notice";

/**
 * 백엔드가 아직 없는 화면의 자리표시자.
 *
 * 디자인의 목록·폼을 껍데기로 흉내 내지 않는 게 핵심이다. 가짜 충전소 세 개나
 * 눌러도 아무 일 없는 로그인 버튼은 시연에서 질문 한 번에 들통나고, 그때 잃는
 * 신뢰가 "준비 중"이라고 적어서 잃는 것보다 크다. 대신 화면 이름은 그대로 두어
 * 어디에 무엇이 들어올지는 보이게 하고, 못 여는 이유를 한 줄로 밝힌다.
 *
 * 막다른 길로 두지 않으려고 지금 동작하는 화면으로 가는 링크를 항상 붙인다.
 */
export function ComingSoon({
  title,
  reason,
  children,
}: {
  title: string;
  /** 왜 아직 못 여는지 — 연동이 필요한 대상까지 적는다 */
  reason: string;
  /** 이 화면에만 있는 자리표시자 (예: 지도 영역) */
  children?: ReactNode;
}) {
  return (
    <section className="mx-auto w-full max-w-[640px] pb-10">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight lg:text-[32px]">{title}</h1>
        <Badge tone="off">준비 중</Badge>
      </div>

      {children ? <div className="mt-5">{children}</div> : null}

      <Notice className="mt-5">{reason}</Notice>

      <div className="mt-6 flex flex-wrap gap-2.5">
        <ButtonLink href="/recommend">충전 시간 추천받기</ButtonLink>
        <ButtonLink href="/timeline" variant="outline">
          하루 단가 보기
        </ButtonLink>
        <ButtonLink href="/" variant="ghost">
          홈으로
        </ButtonLink>
      </div>
    </section>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { ArrowRightIcon, ChevronRightIcon } from "@/components/shell/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { ApiError } from "@/lib/api/client";
import { deleteAccount, fetchPlanSummary, fetchVehicles } from "@/lib/api/endpoints";
import type { PlanSummary, Vehicle } from "@/lib/api/types";
import { formatWon } from "@/lib/format";

import { useIsHydrated } from "./hooks";
import { currentMonthInSeoul, vehicleSpecLine } from "./me-format";
import { MeLayout, ME_NAV } from "./MeSidebar";
import { DangerButton, MeSkeleton, ServerUnreachable, SignInRequired } from "./MeStates";

/**
 * 마이페이지 요약 (디자인 p-08 모바일 · p-21 데스크톱).
 *
 * 모바일과 데스크톱이 꽤 다르게 생겼지만 DOM은 한 벌만 만든다. 같은 내용을 두 번
 * 그려 하나를 CSS로 숨기면 스크린리더가 같은 문장을 두 번 읽고, 고칠 때도 두 곳을
 * 고쳐야 한다. 대신 lg: 변형으로 카드의 톤과 배치를 바꾼다 — Tailwind 출력에서
 * lg: 변형이 기본 유틸리티보다 뒤에 오므로 bg-ink → lg:bg-surface 같은 덮어쓰기가 먹는다.
 *
 * 즐겨찾는 충전소 숫자는 **일부러 부르지 않는다.** 백엔드가 즐겨찾기 응답 모델을
 * 분리하는 중이라, 지금 값을 받아 그리면 모델이 바뀐 날 조용히 틀린 숫자가 뜬다.
 */
export function MeSummary() {
  const { status, user, signOut, clear } = useSession();
  const router = useRouter();

  const [vehicles, setVehicles] = useState<Vehicle[] | null>(null);
  const [summary, setSummary] = useState<PlanSummary | null>(null);

  /* 탈퇴 확인 단계. window.confirm은 쓰지 않는다 — 브라우저 모달은 자동화가 못 넘고,
   * 무엇보다 비밀번호를 받을 칸이 없다. */
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [withdrawError, setWithdrawError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  /* '이번 달'은 붙은 다음에 계산한다. 이유는 hooks.ts에 적어 두었다. */
  const hydrated = useIsHydrated();
  const month = hydrated ? currentMonthInSeoul() : null;

  useEffect(() => {
    if (status !== "authenticated") return;
    let live = true;
    fetchVehicles()
      .then((list) => {
        if (live) setVehicles(list);
      })
      .catch((error: unknown) => {
        if (!live) return;
        // 401은 세션이 끊긴 것이다. 세션을 비우면 아래 분기가 로그인 안내로 떨어뜨린다.
        if (error instanceof ApiError && error.needsLogin) clear();
      });
    return () => {
      live = false;
    };
  }, [status, clear]);

  useEffect(() => {
    if (status !== "authenticated" || month === null) return;
    let live = true;
    fetchPlanSummary(month)
      .then((data) => {
        if (live) setSummary(data);
      })
      .catch((error: unknown) => {
        if (!live) return;
        if (error instanceof ApiError && error.needsLogin) clear();
        // 그 밖의 실패는 "—"로 남긴다. 요약 한 줄 때문에 화면 전체를 막지 않는다.
      });
    return () => {
      live = false;
    };
  }, [status, month, clear]);

  if (status === "loading") return <MeSkeleton />;
  if (status === "unreachable") return <ServerUnreachable title="내 정보" />;
  if (status === "anonymous" || user === null) {
    return (
      <SignInRequired
        next="/me"
        description="기본 차량과 저장한 충전 계획, 즐겨찾는 충전소는 로그인한 뒤에 보여드릴 수 있어요."
      />
    );
  }

  const defaultVehicle = vehicles?.find((vehicle) => vehicle.is_default) ?? null;
  const countText = summary ? `${summary.count}건` : "—";
  const savingsText = summary ? formatWon(summary.total_savings_won) : "—";

  async function handleLogout() {
    setPending(true);
    await signOut();
    // 로그아웃하고 이 화면에 남으면 "로그인이 필요해요"만 보인다. 홈이 더 쓸모 있다.
    router.replace("/");
  }

  async function handleWithdraw(event: FormEvent) {
    event.preventDefault();
    if (password.trim() === "") {
      // 비밀번호 없이 보내면 서버가 422로 되돌려준다. 그 왕복을 사용자에게 시키지 않는다.
      setWithdrawError("비밀번호를 입력해 주세요.");
      return;
    }
    setPending(true);
    setWithdrawError(null);
    try {
      await deleteAccount(password);
      clear(); /* 서버 세션은 이미 사라졌다. 화면도 손님으로 되돌린다. */
      router.replace("/");
    } catch (error: unknown) {
      setWithdrawError(
        error instanceof ApiError ? error.message : "탈퇴하지 못했습니다.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <MeLayout>
      <h1 className="text-2xl font-bold tracking-tight text-ink lg:text-[32px]">
        {user.nickname ?? user.email} 님
      </h1>
      <p className="mt-1 text-sm text-ink-3">{user.email}</p>

      <div className="mt-5 grid gap-3 lg:mt-6 lg:grid-cols-3 lg:items-start lg:gap-5">
        {/* 기본 차량 — 모바일은 검정 카드(p-08), 데스크톱은 흰 카드(p-21) */}
        <Card tone="ink" className="p-5 lg:border lg:border-line lg:bg-surface lg:text-ink">
          <p className="text-xs font-bold text-white/60 lg:text-ink-3">기본 차량</p>
          {defaultVehicle ? (
            <>
              <p className="mt-2 text-xl font-bold lg:text-[22px]">{defaultVehicle.name}</p>
              <p className="tnum mt-2 text-sm text-white/80 lg:text-ink-2">
                {vehicleSpecLine(defaultVehicle)}
              </p>
            </>
          ) : vehicles === null ? (
            <div
              className="mt-3 h-10 animate-pulse rounded-field bg-white/15 lg:bg-sunken"
              aria-hidden
            />
          ) : (
            <>
              <p className="mt-2 text-lg font-bold">기본 차량이 아직 없어요</p>
              <p className="mt-2 text-sm text-white/80 lg:text-ink-2">
                차량을 등록해 두면 여기에서 바로 확인할 수 있어요.
              </p>
            </>
          )}

          {/*
           * 기본 차량이 있으면 이 링크는 데스크톱 전용이다(p-21의 "차량 관리").
           * 모바일에는 아래 목록에 "내 차량" 줄이 이미 있어 두 번 놓을 이유가 없다.
           * 없을 때는 모바일에서도 바로 등록하러 갈 수 있어야 하므로 항상 띄운다.
           */}
          <Link
            href="/me/vehicles"
            className={`mt-4 text-sm font-bold ${
              defaultVehicle
                ? "hidden text-brand lg:inline-block"
                : "inline-block text-accent lg:text-brand"
            }`}
          >
            {defaultVehicle ? "차량 관리" : "차량 등록하기"}
          </Link>
        </Card>

        {/*
         * 이번 달 계획.
         * 모바일은 흰 칸 + 라임 칸 두 장(p-08), 데스크톱은 한 카드 안의 두 줄(p-21).
         * 같은 내용을 두 번 그리지 않으려고 안쪽 그리드를 lg에서 한 열로 접는다.
         */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-1 lg:gap-0 lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-5">
          <Card className="p-4 lg:rounded-none lg:border-0 lg:bg-transparent lg:p-0">
            <p className="text-xs font-bold text-ink-3">
              이번 달 저장<span className="hidden lg:inline">한 계획</span>
            </p>
            <p className="tnum mt-2 text-xl font-bold text-ink lg:text-[22px]">{countText}</p>
          </Card>

          <Card
            tone="accent"
            className="p-4 lg:mt-2 lg:rounded-none lg:bg-transparent lg:p-0"
          >
            <p className="text-xs font-bold text-ink/70 lg:text-ink-3">예상 절감 합계</p>
            <p className="tnum mt-2 text-xl font-bold lg:mt-0.5 lg:text-base">{savingsText}</p>
          </Card>

          <Link
            href="/me/plans"
            className="mt-4 hidden text-sm font-bold text-brand lg:inline-block"
          >
            충전 기록
          </Link>
        </div>

        {/* 즐겨찾는 충전소 — 숫자를 부르지 않는 이유는 파일 머리말에 적었다. */}
        <Card className="hidden p-5 lg:block">
          <p className="text-xs font-bold text-ink-3">즐겨찾는 충전소</p>
          <p className="mt-2 text-xl font-bold text-ink lg:text-[22px]">준비 중</p>
          <p className="mt-2 text-sm text-ink-2">
            충전소 응답 형식을 정리하는 중이라 아직 개수를 보여드리지 않아요.
          </p>
          <Link href="/me/favorites" className="mt-4 inline-block text-sm font-bold text-brand">
            즐겨찾기
          </Link>
        </Card>
      </div>

      {/* 데스크톱 배너 (p-21). 기본 차량이 없으면 약속할 게 없으니 띄우지 않는다. */}
      {defaultVehicle ? (
        <Link
          href="/recommend"
          className="mt-5 hidden items-center justify-between gap-4 rounded-card bg-ink px-7 py-6 text-white transition-colors hover:bg-ink/90 lg:flex"
        >
          <span>
            <span className="block text-lg font-bold">기본 차량으로 바로 추천받기</span>
            {/*
             * 디자인의 "배터리 용량과 충전기 출력이 자동으로 채워져요" 대신 실제 값을 적는다.
             * 추천 폼이 아직 차량 정보를 넘겨받지 않아서, 그 문장은 지금은 거짓말이 된다.
             */}
            <span className="tnum mt-1 block text-sm text-white/70">
              {defaultVehicle.name} · {vehicleSpecLine(defaultVehicle)}
            </span>
          </span>
          <ArrowRightIcon className="size-6 shrink-0" />
        </Link>
      ) : null}

      {/* 모바일 목록 (p-08). 데스크톱에서는 좌측 사이드바가 같은 일을 한다. */}
      <div className="mt-3 grid gap-2 lg:hidden">
        {ME_NAV.filter((item) => item.href !== "/me").map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="flex items-center justify-between gap-3 rounded-card border border-line bg-surface px-4 py-4"
          >
            <span className="text-[15px] font-bold text-ink">{item.label}</span>
            <span className="flex items-center gap-2">
              {item.href === "/me/favorites" ? <Badge tone="off">준비 중</Badge> : null}
              <ChevronRightIcon className="size-5 text-ink-3" />
            </span>
          </Link>
        ))}
      </div>

      {/* 계정 — 모바일은 버튼 두 개(p-08), 데스크톱은 설명이 붙은 카드(p-21) */}
      <section className="mt-6 lg:mt-10">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between lg:rounded-card lg:border lg:border-line lg:bg-surface lg:p-6">
          <div className="hidden lg:block">
            <h2 className="text-base font-bold text-ink">계정</h2>
            <p className="mt-1 text-sm text-ink-2">
              탈퇴하면 차량·충전 기록·즐겨찾기가 모두 삭제돼요.
            </p>
          </div>
          <div className="flex flex-col items-center gap-3 lg:flex-row lg:gap-4">
            <Button
              variant="outline"
              size="lg"
              className="w-full lg:h-11 lg:w-auto"
              onClick={() => void handleLogout()}
              disabled={pending}
            >
              로그아웃
            </Button>
            <DangerButton
              aria-expanded={withdrawOpen}
              onClick={() => {
                setWithdrawOpen((open) => !open);
                setWithdrawError(null);
              }}
            >
              회원 탈퇴
            </DangerButton>
          </div>
        </div>

        {/* 확인 단계는 인라인으로 편다. 모달이 아니어서 뒤로 가기·스크롤이 그대로 산다. */}
        {withdrawOpen ? (
          <form
            onSubmit={(event) => void handleWithdraw(event)}
            className="mt-3 rounded-card border border-line bg-surface p-5"
          >
            <h3 className="text-base font-bold text-ink">정말 탈퇴할까요?</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
              등록한 차량과 저장한 충전 기록, 즐겨찾는 충전소가 모두 삭제되고 되돌릴 수
              없어요. 계속하려면 비밀번호를 한 번 더 입력해 주세요.
            </p>
            <Field
              label="비밀번호"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              error={withdrawError ?? undefined}
              className="mt-4 max-w-[320px]"
            />
            <div className="mt-4 flex gap-2">
              <Button type="submit" variant="dark" disabled={pending}>
                탈퇴하기
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setWithdrawOpen(false);
                  setPassword("");
                  setWithdrawError(null);
                }}
              >
                취소
              </Button>
            </div>
          </form>
        ) : null}
      </section>
    </MeLayout>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { ChevronLeftIcon } from "@/components/shell/icons";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api/client";
import {
  createVehicle,
  deleteVehicle,
  fetchVehicles,
  updateVehicle,
} from "@/lib/api/endpoints";
import type { Vehicle, VehicleInput } from "@/lib/api/types";

import { MeLayout } from "./MeSidebar";
import { LoadFailure, MeSkeleton, ServerUnreachable, SignInRequired } from "./MeStates";
import { VehicleForm } from "./VehicleForm";
import { VehicleList } from "./VehicleList";

/**
 * 내 차량 (F-12, 디자인 p-09 모바일 · p-22 데스크톱 · p-10 모바일 추가 폼).
 *
 * 폼을 별도 라우트로 빼지 않았다. 목록과 폼이 같은 데이터를 보고, 저장이 끝나면
 * 목록을 다시 불러야 하는데, 라우트를 나누면 그 "다시 불러오기"를 라우터 새로고침에
 * 기대야 한다. 대신 모바일에서는 폼이 목록을 덮어 p-10처럼 전체 화면이 되고,
 * 데스크톱에서는 오른쪽에 상시 카드로 남는다 — CSS 한 줄 차이다.
 *
 * 목록은 무엇을 바꾸든 서버에서 다시 받는다. 특히 기본 차량은 서버가 **다른 차량의**
 * is_default를 함께 해제하는 부수효과를 낸다. 화면이 그걸 흉내 내면(낙관적 갱신)
 * 서버가 실제로 한 일과 어긋날 수 있고, 어긋난 걸 알아챌 방법도 없다.
 */

type Load =
  | { status: "loading" }
  | { status: "ready"; vehicles: Vehicle[] }
  | { status: "error"; message: string };

export function VehiclesScreen() {
  const { status, clear } = useSession();

  /*
   * 결과를 "어떤 요청의 결과인지"(key)와 함께 들고 있는다. 로딩 여부를 따로 state로
   * 두면 다시 불러오는 사이에 옛 목록이 한 프레임 남고, 늦게 온 응답이 새 목록을
   * 덮어쓸 자리도 생긴다. 키가 다르면 그냥 로딩이다 — 어긋날 수가 없다.
   */
  const [reloadCount, setReloadCount] = useState(0);
  const [result, setResult] = useState<{ key: string; load: Load } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  /** 수정 중인 차량. null이면 폼은 추가 모드다. */
  const [editing, setEditing] = useState<Vehicle | null>(null);
  /** 모바일에서 폼이 목록을 덮고 있는가. 데스크톱에서는 폼이 늘 보이므로 영향이 없다. */
  const [formOpen, setFormOpen] = useState(false);
  /** 저장 뒤 폼을 비우려고 key를 바꾼다 — 칸을 하나씩 되돌리는 코드를 없앤다. */
  const [formSeq, setFormSeq] = useState(0);

  const requestKey = status === "authenticated" ? `vehicles|${reloadCount}` : null;
  const load: Load =
    requestKey !== null && result?.key === requestKey ? result.load : { status: "loading" };

  useEffect(() => {
    if (status !== "authenticated") return;
    const key = `vehicles|${reloadCount}`;
    let live = true;
    fetchVehicles()
      .then((vehicles) => {
        if (live) setResult({ key, load: { status: "ready", vehicles } });
      })
      .catch((error: unknown) => {
        if (!live) return;
        // 401은 세션이 끊긴 것이다. 세션을 비우면 아래 분기가 로그인 안내로 떨어뜨린다.
        if (error instanceof ApiError && error.needsLogin) {
          clear();
          return;
        }
        setResult({
          key,
          load: {
            status: "error",
            message:
              error instanceof ApiError ? error.message : "차량을 불러오지 못했습니다.",
          },
        });
      });
    return () => {
      live = false;
    };
  }, [status, reloadCount, clear]);

  if (status === "loading") return <MeSkeleton />;
  if (status === "unreachable") return <ServerUnreachable title="내 차량" />;
  if (status === "anonymous") {
    return (
      <SignInRequired
        next="/me/vehicles"
        description="등록한 차량은 계정에 저장돼요. 로그인하면 바로 이어서 관리할 수 있어요."
      />
    );
  }

  const reload = () => setReloadCount((count) => count + 1);

  /** 목록을 바꾸는 요청이 실패했을 때. 401이면 로그인 안내로 떨어진다. */
  function reportActionError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.needsLogin) {
      clear();
      return;
    }
    setActionError(error instanceof ApiError ? error.message : fallback);
  }

  /** 폼 제출. 실패는 그대로 던져 폼이 자기 자리에서 이유를 띄우게 한다. */
  async function handleSave(input: VehicleInput) {
    setActionError(null);
    if (editing) {
      // PATCH는 지금 full-replace다. 폼이 전 필드를 채워 주므로 그대로 보낸다.
      await updateVehicle(editing.id, input);
    } else {
      await createVehicle(input);
    }
    setEditing(null);
    setFormOpen(false);
    setFormSeq((seq) => seq + 1);
    reload();
  }

  async function handleMakeDefault(vehicle: Vehicle) {
    setBusyId(vehicle.id);
    setActionError(null);
    try {
      /*
       * is_default만 보내면 나머지 필드가 날아간다(full-replace). 그리고 서버가
       * 기존 기본 차량을 자동 해제하므로, 해제 요청을 따로 보내면 안 된다.
       */
      await updateVehicle(vehicle.id, {
        name: vehicle.name,
        battery_kwh: vehicle.battery_kwh,
        charger_kw: vehicle.charger_kw,
        mode: vehicle.mode,
        is_default: true,
      });
      reload();
    } catch (error: unknown) {
      reportActionError(error, "기본 차량을 바꾸지 못했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(vehicle: Vehicle) {
    setBusyId(vehicle.id);
    setActionError(null);
    try {
      await deleteVehicle(vehicle.id);
      // 지운 차를 수정하던 중이었다면 폼도 닫아야 한다.
      if (editing?.id === vehicle.id) {
        setEditing(null);
        setFormOpen(false);
      }
      reload();
    } catch (error: unknown) {
      reportActionError(error, "차량을 삭제하지 못했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  const vehicles = load.status === "ready" ? load.vehicles : [];

  return (
    <MeLayout>
      <header className="flex items-center gap-1">
        <Link
          href="/me"
          aria-label="마이페이지"
          className="-ml-2 inline-flex size-11 items-center justify-center rounded-lg text-ink transition-colors duration-150 hover:bg-sunken lg:hidden"
        >
          <ChevronLeftIcon />
        </Link>
        <h1 className="text-title text-ink lg:text-title-lg">내 차량</h1>
      </header>

      <div className="mt-5 lg:mt-6 lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start lg:gap-6">
        {/* 목록. 모바일에서 폼이 열리면 폼이 이 자리를 덮는다(p-10). */}
        <section className={formOpen ? "hidden lg:block" : ""}>
          {actionError ? (
            <LoadFailure message={actionError} />
          ) : null}

          {load.status === "loading" ? (
            <div className="grid gap-3" aria-hidden>
              {[0, 1].map((index) => (
                <div key={index} className="h-28 animate-pulse rounded-card bg-sunken" />
              ))}
            </div>
          ) : load.status === "error" ? (
            <LoadFailure message={load.message} onRetry={reload} />
          ) : vehicles.length === 0 ? (
            <div className="rounded-card border border-line bg-surface p-6 text-center">
              <p className="text-base font-bold text-ink">아직 등록한 차량이 없어요</p>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">
                차량을 등록하면 배터리 용량과 충전기 출력을 매번 다시 입력하지 않아도 돼요.
              </p>
            </div>
          ) : (
            <>
              <VehicleList
                vehicles={vehicles}
                busyId={busyId}
                onEdit={(vehicle) => {
                  setEditing(vehicle);
                  setFormOpen(true);
                }}
                onMakeDefault={(vehicle) => void handleMakeDefault(vehicle)}
                onDelete={(vehicle) => void handleDelete(vehicle)}
              />
              <p className="mt-3 text-sm leading-relaxed text-ink-2">
                기본 차량은 1대예요. 다른 차량을 기본으로 바꾸면 기존 기본은 해제돼요.
              </p>
            </>
          )}

          {/* 모바일에만 있는 버튼. 데스크톱은 오른쪽 카드가 늘 열려 있다(p-22). */}
          <Button
            type="button"
            size="lg"
            className="mt-5 w-full lg:hidden"
            onClick={() => {
              setEditing(null);
              setFormSeq((seq) => seq + 1);
              setFormOpen(true);
            }}
          >
            <span aria-hidden>＋</span> 차량 추가
          </Button>
        </section>

        <aside className={formOpen ? "" : "hidden lg:block"}>
          <VehicleForm
            key={editing ? `edit-${editing.id}` : `new-${formSeq}`}
            initial={editing}
            onSubmit={handleSave}
            onCancel={() => {
              setEditing(null);
              setFormOpen(false);
            }}
          />
        </aside>
      </div>
    </MeLayout>
  );
}

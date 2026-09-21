"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { fetchVehicles } from "@/lib/api/endpoints";
import type { Vehicle } from "@/lib/api/types";

/**
 * 추천 화면에서 쓸 내 차량 목록.
 *
 * 손님에게는 아예 부르지 않는다. 401이 뻔한 요청을 보낼 이유가 없고, 세션 확인이
 * 끝나기 전에 부르면 로그인한 사용자에게도 한 번 401이 난다.
 *
 * 실패는 조용히 빈 목록으로 흘린다. 이 화면의 본래 목적은 로그인 없이도 쓸 수 있는
 * 것이라, 차량을 못 불러왔다고 직접 입력까지 막으면 안 된다.
 */
export function useMyVehicles(): { vehicles: Vehicle[]; loaded: boolean } {
  const { status } = useSession();
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    let alive = true;
    fetchVehicles()
      .then((mine) => {
        if (alive) setVehicles(mine);
      })
      .catch(() => {
        if (alive) setVehicles([]);
      })
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [status]);

  return { vehicles, loaded };
}

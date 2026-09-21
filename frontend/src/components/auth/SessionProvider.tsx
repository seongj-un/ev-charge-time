"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/client";
import { fetchMe, logout as requestLogout } from "@/lib/api/endpoints";
import type { User } from "@/lib/api/types";

/**
 * 로그인 상태를 한 곳에서만 판단한다.
 *
 * 세션이 httpOnly 쿠키라 자바스크립트가 읽을 수 없다. "로그인했나?"를 아는
 * 유일한 방법은 GET /api/me를 불러 401인지 보는 것이다. 화면마다 이걸 하면
 * 같은 요청이 네 번 나가고, 화면마다 로딩 처리가 제각각이 된다.
 */

export type SessionStatus =
  /** 아직 /api/me 응답을 못 받았다. 로그인 여부를 단정하면 안 된다. */
  | "loading"
  | "authenticated"
  | "anonymous"
  /** 백엔드에 닿지 못했다. 손님과 구분해야 "로그인하세요"로 오도하지 않는다. */
  | "unreachable";

type SessionValue = {
  status: SessionStatus;
  user: User | null;
  /** 로그인·회원가입 응답이 준 사용자를 그대로 받는다. /api/me를 또 부르지 않는다. */
  signIn: (user: User) => void;
  signOut: () => Promise<void>;
  /** 탈퇴처럼 서버 쪽에서 이미 세션이 사라진 경우 화면만 손님으로 되돌린다. */
  clear: () => void;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    let alive = true;
    fetchMe()
      .then((me) => {
        if (!alive) return;
        setUser(me);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setUser(null);
        // status 0은 서버에 닿지 못한 것이다. 이걸 손님으로 처리하면
        // 백엔드가 꺼졌을 때 "로그인하세요"가 떠서 원인을 영영 못 찾는다.
        setStatus(error instanceof ApiError && error.status === 0 ? "unreachable" : "anonymous");
      });
    return () => {
      alive = false;
    };
  }, []);

  const signIn = useCallback((next: User) => {
    setUser(next);
    setStatus("authenticated");
  }, []);

  const clear = useCallback(() => {
    setUser(null);
    setStatus("anonymous");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await requestLogout();
    } catch {
      // 요청이 실패해도 화면은 손님으로 되돌린다. 사용자가 "로그아웃"을
      // 눌렀는데 로그인 상태로 남아 있으면 공용 PC에서 위험하다.
    }
    clear();
  }, [clear]);

  return (
    <SessionContext.Provider value={{ status, user, signIn, signOut, clear }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) {
    // 조용히 손님으로 처리하면 "왜 로그인이 안 잡히지"를 한참 찾게 된다.
    throw new Error("useSession은 SessionProvider 안에서만 쓸 수 있습니다.");
  }
  return value;
}

"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
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
  /**
   * 서버 세션을 지운 뒤에만 손님으로 바꾼다. 요청이 실패하면 로그인 상태를 그대로
   * 두고 예외를 던진다 — 호출한 화면이 실패를 알리고 다시 누르게 해야 한다.
   */
  signOut: () => Promise<void>;
  /** 탈퇴처럼 서버 쪽에서 이미 세션이 사라진 경우 화면만 손님으로 되돌린다. */
  clear: () => void;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<User | null>(null);
  /*
   * 로그인·로그아웃이 일어날 때마다 올린다. 처음 /api/me는 보낸 시점의 값을 들고
   * 있다가, 돌아왔을 때 값이 바뀌었으면 결과를 버린다. 그러지 않으면 늦게 도착한
   * 응답(손님 시절의 401, 이전 사용자)이 그 사이에 끝난 로그인을 덮어쓴다.
   */
  const epoch = useRef(0);

  useEffect(() => {
    let alive = true;
    const sentAt = epoch.current;
    const current = () => alive && epoch.current === sentAt;
    fetchMe()
      .then((me) => {
        if (!current()) return;
        setUser(me);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (!current()) return;
        setUser(null);
        /*
         * 401만 "손님"이다. 나머지는 전부 "판단할 수 없음"이다.
         *
         * 401이 아닌 것을 손님으로 처리하면, 백엔드가 꺼졌을 때(Next rewrite 프록시가
         * 500을 돌려준다) "로그인하세요"가 떠서 사용자가 로그인을 시도하고 또 실패한다.
         * 원인을 영영 못 찾는다.
         */
        const isAnonymous = error instanceof ApiError && error.status === 401;
        setStatus(isAnonymous ? "anonymous" : "unreachable");
      });
    return () => {
      alive = false;
    };
  }, []);

  const signIn = useCallback((next: User) => {
    epoch.current += 1;
    setUser(next);
    setStatus("authenticated");
  }, []);

  const clear = useCallback(() => {
    epoch.current += 1;
    setUser(null);
    setStatus("anonymous");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await requestLogout();
    } catch (error: unknown) {
      /*
       * 401은 서버에 세션이 이미 없다는 뜻이다. 그때만 손님으로 돌린다.
       *
       * 그 밖의 실패에서 화면만 손님으로 돌리면 서버 세션과 쿠키는 그대로라,
       * 새로고침하는 순간 다시 로그인된다. 공용 PC에서 "로그아웃됐다"고 믿고
       * 자리를 뜨게 만드는 쪽이 더 위험하다. 예외를 그대로 올려 화면이 알리게 한다.
       */
      if (!(error instanceof ApiError && error.needsLogin)) throw error;
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

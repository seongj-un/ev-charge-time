"use client";

import { useEffect, useRef, useState } from "react";

import { useSession } from "@/components/auth/SessionProvider";
import { PageContainer } from "@/components/shell/AppShell";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { ApiError } from "@/lib/api/client";
import { askChat } from "@/lib/api/endpoints";
import type { RecommendResponse } from "@/lib/api/types";
import { formatHm, formatKoreanDate, formatKwh, formatWon } from "@/lib/format";
import { unverifiedNotice } from "@/lib/tariff";

import {
  FALLBACK_WAIT_SECONDS,
  missingLabels,
  msUntilUnlock,
  toHistory,
  unlockAt,
  waitLabel,
} from "./ask-view";
import type { AskTurn } from "./ask-view";

/**
 * /ask — F-10 자연어 질의.
 *
 * **모델은 숫자를 쓰지 않는다.** 질문에서 조건만 뽑는 것이 모델의 일이고,
 * 금액과 시각은 서버가 `compute_recommendation`으로 계산해 `recommendation`에
 * 담아 보낸다 (API 명세서 7-8). 그래서 이 화면은 answer 문장을 절대 파싱하지
 * 않고, 숫자는 전부 그 객체에서 꺼낸다. 문장과 객체가 어긋나면 믿을 것은
 * 객체다 — 사용자는 여기 적힌 시각에 실제로 차를 꽂는다.
 */

/** 막힌 이유. 넷을 서로 다르게 말해야 사용자가 다음에 무엇을 할지 안다. */
type Blocked =
  | { kind: "none" }
  /** GEMINI_API_KEY가 없다. 기다린다고 풀리지 않는다. */
  | { kind: "not-ready"; message: string }
  /**
   * 호출 제한. 재시도 버튼을 주지 않는다 — 눌러도 또 429다.
   * 대신 `unlockAtMs`에 스스로 풀린다. 시각을 모르면 FALLBACK_WAIT_SECONDS 뒤다.
   */
  | { kind: "rate-limited"; message: string; until: string; unlockAtMs: number }
  /** 모델 쪽 일시 실패. 같은 질문을 그대로 다시 보낼 수 있다. */
  | { kind: "retryable"; message: string; question: string };

export function AskScreen() {
  const { status } = useSession();
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [blocked, setBlocked] = useState<Blocked>({ kind: "none" });
  const logEndRef = useRef<HTMLDivElement>(null);

  /* 새 답이 오면 그쪽으로 따라 내려간다. 스크롤을 직접 올린 뒤에는 방해하지 않는다. */
  useEffect(() => {
    if (turns.length === 0) return;
    logEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [turns.length]);

  /*
   * 호출 제한은 풀리는 시각에 스스로 푼다. 안 풀면 화면에 적힌 시각이 지나도
   * 입력창이 잠긴 채라 새로고침 말고는 다시 물어볼 길이 없다.
   *
   * blocked가 바뀌거나 화면을 떠나면 타이머를 치운다. 남겨 두면 나중에 다른
   * 이유로 막힌 상태(503 등)를 이 타이머가 엉뚱하게 지운다.
   */
  const unlockAtMs = blocked.kind === "rate-limited" ? blocked.unlockAtMs : null;
  useEffect(() => {
    if (unlockAtMs === null) return;
    const timer = setTimeout(
      () => setBlocked({ kind: "none" }),
      msUntilUnlock(unlockAtMs, Date.now()),
    );
    return () => clearTimeout(timer);
  }, [unlockAtMs]);

  async function send(question: string, previous: AskTurn[]) {
    setSending(true);
    setBlocked({ kind: "none" });
    try {
      const history = toHistory(previous);
      const reply = await askChat({ message: question, history });
      setTurns((current) => [
        ...current,
        {
          role: "assistant",
          text: reply.answer,
          recommendation: reply.recommendation,
          missingFields: reply.missing_fields,
        },
      ]);
    } catch (error: unknown) {
      setBlocked(blockedFrom(error, question));
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (question === "" || sending || blocked.kind === "rate-limited") return;

    /*
     * 질문을 먼저 화면에 남긴다. 실패해도 남아 있어야 사용자가 무엇을 물었는지
     * 알고, 503이면 그 글로 그대로 다시 보낼 수 있다.
     */
    const previous = turns;
    setTurns([...previous, { role: "user", text: question }]);
    setDraft("");
    void send(question, previous);
  }

  function handleRetry() {
    if (blocked.kind !== "retryable") return;
    // 마지막 사용자 질문은 이미 turns에 들어 있다. 이력에서는 빼고 보낸다.
    void send(blocked.question, turns.slice(0, -1));
  }

  return (
    <PageContainer className="pb-10">
      <h1 className="text-title lg:text-title-lg">질문으로 충전 시간 찾기</h1>
      <p className="mt-3 max-w-[42rem] text-base leading-relaxed text-ink-2">
        말하듯 물어보면 조건을 읽어 추천합니다. 예를 들어 &ldquo;70kWh 배터리를 7kW로 30%에서
        60%까지, 오늘 저녁 6시부터 내일 아침 8시 사이에&rdquo;처럼요.
      </p>

      {status === "loading" ? (
        <p role="status" className="mt-6 text-sm text-ink-2">
          불러오고 있어요…
        </p>
      ) : null}

      {status === "unreachable" ? (
        <Notice className="mt-5">
          서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인하세요. 로그인 여부를 확인하지
          못해 질문을 보내지 않았습니다.
        </Notice>
      ) : null}

      {status === "anonymous" ? <SignInCard /> : null}

      {status === "authenticated" ? (
        <>
          <Transcript turns={turns} endRef={logEndRef} />

          {blocked.kind !== "none" ? (
            <BlockedNotice blocked={blocked} onRetry={handleRetry} />
          ) : null}

          <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-2.5 lg:mt-6">
            <label htmlFor="ask-input" className="text-sm font-bold">
              질문
            </label>
            <textarea
              id="ask-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={3}
              disabled={blocked.kind === "rate-limited"}
              placeholder="내일 출근 전까지 80% 채우려면 언제 충전해?"
              className="w-full resize-y rounded-field border border-line bg-field px-4 py-3 text-base leading-relaxed text-ink placeholder:text-ink-3 hover:border-ink-3 focus-visible:border-brand focus-visible:outline-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            />
            <div className="flex items-center gap-3">
              <Button
                type="submit"
                disabled={sending || blocked.kind === "rate-limited" || draft.trim() === ""}
              >
                {sending ? "물어보는 중…" : "질문 보내기"}
              </Button>
              {/*
               * 한도를 미리 적는다. 20번째 질문에서 처음 알게 되면 시연 도중에
               * 막히고, 그때는 되돌릴 방법이 없다.
               */}
              <span className="text-sm text-ink-2">시간당 20번까지 물어볼 수 있어요</span>
            </div>
          </form>
        </>
      ) : null}
    </PageContainer>
  );
}

function SignInCard() {
  return (
    <Card className="mt-5 p-6 lg:mt-6 lg:p-8">
      <h2 className="text-section">로그인이 필요해요</h2>
      <p className="mt-2 max-w-[32rem] text-sm leading-relaxed text-ink-2">
        질문은 계정마다 시간당 20번으로 제한됩니다. 한 사람이 공용 한도를 다 쓰면 다른
        사람의 질문이 전부 막히기 때문이에요. 조건을 직접 입력하는 추천은 로그인 없이도
        그대로 쓸 수 있습니다.
      </p>
      <div className="mt-6 flex flex-wrap gap-2.5">
        <ButtonLink href={`/login?next=${encodeURIComponent("/ask")}`} size="lg">
          로그인하기
        </ButtonLink>
        <ButtonLink href="/recommend" variant="outline" size="lg">
          조건 입력해서 추천받기
        </ButtonLink>
      </div>
    </Card>
  );
}

function Transcript({
  turns,
  endRef,
}: {
  turns: AskTurn[];
  endRef: React.RefObject<HTMLDivElement | null>;
}) {
  if (turns.length === 0) return null;
  return (
    <div
      role="log"
      aria-label="대화"
      aria-live="polite"
      className="mt-6 flex flex-col gap-4 lg:mt-7"
    >
      {turns.map((turn, index) =>
        turn.role === "user" ? (
          <p
            key={index}
            className="max-w-[36rem] self-end rounded-card bg-brand px-4 py-3 text-sm leading-relaxed text-surface"
          >
            {turn.text}
          </p>
        ) : (
          <div key={index} className="max-w-[42rem] self-start">
            <p className="rounded-card bg-surface px-4 py-3 text-sm leading-relaxed text-ink">
              {turn.text}
            </p>
            {turn.missingFields.length > 0 ? <Missing fields={turn.missingFields} /> : null}
            {turn.recommendation ? <PlanCard plan={turn.recommendation} /> : null}
          </div>
        ),
      )}
      <div ref={endRef} aria-hidden />
    </div>
  );
}

/**
 * 되물어야 할 항목.
 *
 * 문장만 있으면 사용자는 무엇을 빠뜨렸는지 다시 읽어 찾아야 한다. 목록으로
 * 세워 두면 하나씩 채워 넣기만 하면 된다.
 */
function Missing({ fields }: { fields: string[] }) {
  return (
    <div className="mt-2.5 rounded-card bg-sunken px-4 py-3">
      <p className="text-sm font-bold text-ink-2">더 알려주실 것</p>
      <ul
        aria-label="더 알려주실 것"
        className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-sm text-ink"
      >
        {/*
         * 가운뎃점은 의사요소로 넣는다. 글자로 적으면 스크린리더가 항목마다
         * "가운뎃점"을 읽고, 접근성 이름도 "· 배터리 용량"이 된다.
         */}
        {missingLabels(fields).map((label) => (
          <li key={label} className="before:mr-1 before:text-ink-3 before:content-['·']">
            {label}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 추천 결과 카드.
 *
 * 여기 있는 숫자는 전부 서버가 계산한 값이다. answer 문장에서 꺼내지 않는다 —
 * 모델이 문장을 조금만 다르게 써도 엉뚱한 시각이 뜨고, 사용자는 그 시각에
 * 실제로 차를 꽂는다.
 */
function PlanCard({ plan }: { plan: RecommendResponse }) {
  const notice = unverifiedNotice(plan.unverified_tariff_items);
  return (
    <Card
      role="group"
      aria-label="추천 충전 시간"
      className="mt-2.5 border border-line p-4 lg:p-5"
    >
      <p className="text-sm text-ink-2">{formatKoreanDate(plan.best.start)}</p>
      <p className="mt-1 text-lg font-bold tnum">
        {formatHm(plan.best.start)} – {formatHm(plan.best.end)}
      </p>

      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-sm text-ink-2">충전량</dt>
          <dd className="tnum font-bold">{formatKwh(plan.best.energy_kwh)}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-2">예상 요금</dt>
          <dd className="tnum font-bold">{formatWon(plan.best.cost_won)}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-2">바로 충전 대비</dt>
          <dd className="tnum font-bold text-brand">{formatWon(plan.savings_won)} 절감</dd>
        </div>
      </dl>

      {plan.assumptions.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-0.5 text-sm leading-relaxed text-ink-2">
          {plan.assumptions.map((line) => (
            <li key={line}>· {line}</li>
          ))}
        </ul>
      ) : null}

      {notice ? <Notice className="mt-3">{notice}</Notice> : null}
    </Card>
  );
}

function BlockedNotice({ blocked, onRetry }: { blocked: Blocked; onRetry: () => void }) {
  if (blocked.kind === "none") return null;
  return (
    <div className="mt-4">
      <Notice>
        <p>{blocked.message}</p>
        {blocked.kind === "rate-limited" ? <p className="mt-1">{blocked.until}</p> : null}
      </Notice>
      {blocked.kind === "retryable" ? (
        <Button variant="outline" className="mt-3" onClick={onRetry}>
          다시 시도
        </Button>
      ) : null}
    </div>
  );
}

/**
 * 오류 → 화면이 할 말.
 *
 * 429와 503을 같이 묶지 않는 게 요점이다. 503은 다시 눌러볼 만하고, 429는
 * 눌러봐야 또 429인 데다 그 호출도 무료 티어 할당량을 깎는다.
 */
function blockedFrom(error: unknown, question: string): Blocked {
  if (!(error instanceof ApiError)) {
    return { kind: "retryable", message: "질문을 보내지 못했습니다.", question };
  }
  if (error.status === 501) {
    return { kind: "not-ready", message: error.message };
  }
  if (error.status === 429) {
    const now = Date.now();
    return {
      kind: "rate-limited",
      message: error.message,
      until: waitLabel(error.retryAfterSeconds, now),
      unlockAtMs: unlockAt(error.retryAfterSeconds ?? FALLBACK_WAIT_SECONDS, now),
    };
  }
  return { kind: "retryable", message: error.message, question };
}

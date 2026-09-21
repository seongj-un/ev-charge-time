import { FIELD_LABEL } from "@/lib/api/client";
import type { ChatTurn, RecommendResponse } from "@/lib/api/types";

/**
 * 자연어 질의 화면(F-10)이 쓰는 순수 계산.
 *
 * 여기에 예시 대화나 그럴듯한 답변 같은 상수는 없다. 화면 코드가 답변을
 * 하나라도 들고 있으면 키가 없을 때(501) 그게 새어 나온다 — 모델이 쓴 적
 * 없는 문장을 모델의 답으로 보여주는 셈이다.
 */

/** 대화 한 줄. 사용자 질문이거나 서버의 답이다. */
export type AskTurn =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string;
      /** 서버가 계산한 값. 모델이 쓴 숫자가 아니다. */
      recommendation: RecommendResponse | null;
      missingFields: string[];
    };

/**
 * 서버가 프롬프트에 붙이는 턴 수 (`chat_service._history_lines`의 `history[-6:]`).
 *
 * 보내는 것과 쓰이는 것을 같게 맞춘다. 더 보내도 앞쪽은 조용히 무시되므로,
 * 다르게 두면 "이력을 보냈는데 왜 기억 못 하지"를 디버깅하게 된다.
 */
export const HISTORY_TURNS = 6;

/**
 * 되물어야 할 항목을 우리말로.
 *
 * 번역표는 client.ts의 것 하나를 쓴다. 여기에 또 만들면 백엔드가 필드 이름을
 * 바꿀 때 두 곳이 갈라지고, 한쪽만 고친 화면이 조용히 틀린 말을 한다 —
 * 요금 고지 문구에서 같은 식으로 세 번 당했다.
 */
export function missingLabels(fields: string[]): string[] {
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const field of fields) {
    const label = FIELD_LABEL[field] ?? field;
    if (seen.has(label)) continue;
    seen.add(label);
    labels.push(label);
  }
  return labels;
}

/** 지금부터 `seconds` 뒤. 429의 Retry-After가 초로 온다. */
export function unlockAt(seconds: number, nowMs: number): number {
  return nowMs + seconds * 1000;
}

/**
 * 풀리는 시각을 "23:04"로.
 *
 * 남은 시간을 흘려보내는 카운트다운 대신 시각을 적는다 — 카운트다운은 탭을
 * 두고 자리를 비우면 낡지만 시각은 낡지 않는다.
 *
 * **초가 남아 있으면 다음 분으로 올린다.** 내려서 적으면 그 시각에 눌러도
 * 아직 같은 창이라 또 429가 나고, 사용자는 화면이 틀렸다고 여긴다. 서버가
 * Retry-After를 올림하는 것과 같은 이유다.
 *
 * `timeZone`은 테스트가 고정하려고 받는다. 화면은 넘기지 않는다 — 사용자가
 * 읽는 건 자기 시계이고, 그 시계로 기다리기 때문이다.
 */
export function unlockClockLabel(atMs: number, timeZone?: string): string {
  const rounded = Math.ceil(atMs / 60_000) * 60_000;
  const parts = new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...(timeZone ? { timeZone } : {}),
  }).formatToParts(new Date(rounded));
  const hour = parts.find((part) => part.type === "hour")?.value ?? "00";
  const minute = parts.find((part) => part.type === "minute")?.value ?? "00";
  // ko-KR은 자정을 "24"로 내놓는 구현이 있다. 24:05는 시계에 없는 시각이다.
  return `${hour === "24" ? "00" : hour}:${minute}`;
}

/** 429 밑에 적을 한 줄. 남은 시간을 모르면 시각을 지어내지 않는다. */
export function waitLabel(seconds: number | null, nowMs: number, timeZone?: string): string {
  if (seconds === null) return "잠시 후 다시 물어봐 주세요.";
  return `${unlockClockLabel(unlockAt(seconds, nowMs), timeZone)}부터 다시 물어볼 수 있어요.`;
}

/** 다음 질문에 붙일 이력. 서버가 쓰는 만큼만, 빈 글은 빼고. */
export function toHistory(turns: AskTurn[]): ChatTurn[] {
  return turns
    .map((turn) => ({ role: turn.role, content: turn.text.trim() }))
    .filter((turn) => turn.content !== "")
    .slice(-HISTORY_TURNS);
}

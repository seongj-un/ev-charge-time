import { describe, expect, test } from "vitest";

import {
  HISTORY_TURNS,
  missingLabels,
  toHistory,
  unlockAt,
  unlockClockLabel,
  waitLabel,
} from "./ask-view";
import type { AskTurn } from "./ask-view";

/*
 * 되물을 항목을 우리말로.
 *
 * 백엔드는 `missing_fields`에 필드 이름을 그대로 담는다 — "battery_kwh"가
 * 화면에 뜨면 사용자는 무엇을 적어야 하는지 모른다. 번역표는 client.ts의
 * 것 하나를 쓴다. 여기에 또 만들면 백엔드가 필드 이름을 바꿀 때 두 곳이
 * 갈라지고, 한쪽만 고치면 화면이 조용히 틀린 말을 한다.
 */
describe("되물을 항목", () => {
  test("필드 이름을 우리말로 바꾼다", () => {
    expect(missingLabels(["battery_kwh", "soc_now", "deadline"])).toEqual([
      "배터리 용량",
      "현재 충전량",
      "완료 시각",
    ]);
  });

  /* 백엔드가 새 필드를 추가해도 빈 칸을 내놓지 않는다. */
  test("모르는 필드는 이름을 그대로 남긴다", () => {
    expect(missingLabels(["nonexistent_field"])).toEqual(["nonexistent_field"]);
  });

  test("같은 항목이 두 번 오면 한 번만 말한다", () => {
    expect(missingLabels(["soc_now", "soc_now"])).toEqual(["현재 충전량"]);
  });

  test("빈 배열은 빈 배열이다", () => {
    expect(missingLabels([])).toEqual([]);
  });
});

/*
 * 429의 Retry-After를 화면의 말로.
 *
 * 남은 시간을 흘려보내는 카운트다운 대신 **풀리는 시각**을 적는다. 카운트다운은
 * 탭을 두고 자리를 비우면 낡고, 시각은 낡지 않는다.
 */
describe("다시 물어볼 수 있는 시각", () => {
  const NOW = Date.parse("2026-09-21T22:35:00+09:00");

  test("지금에 남은 초를 더한다", () => {
    expect(unlockAt(1725, NOW)).toBe(NOW + 1725 * 1000);
  });

  test("시:분으로 적는다", () => {
    // 22:35 + 1725초(28분 45초) = 23:03:45 → 23:04에 풀린다
    const label = unlockClockLabel(unlockAt(1725, NOW), "Asia/Seoul");
    expect(label).toBe("23:04");
  });

  /*
   * 올려서 적는다. 내려서 적으면 그 시각에 눌러도 아직 같은 창이라 또 429가
   * 나고, 사용자는 화면이 틀렸다고 여긴다. 서버가 Retry-After를 올림하는 것과
   * 같은 이유다.
   */
  test("초가 남아 있으면 다음 분으로 올린다", () => {
    const at = Date.parse("2026-09-21T23:03:01+09:00");
    expect(unlockClockLabel(at, "Asia/Seoul")).toBe("23:04");
  });

  test("정각이면 올리지 않는다", () => {
    const at = Date.parse("2026-09-21T23:03:00+09:00");
    expect(unlockClockLabel(at, "Asia/Seoul")).toBe("23:03");
  });

  test("자정을 넘으면 넘어간 시각을 적는다", () => {
    const at = Date.parse("2026-09-22T00:05:00+09:00");
    expect(unlockClockLabel(at, "Asia/Seoul")).toBe("00:05");
  });

  /* 서버가 헤더를 안 줬을 때. 없는 시각을 지어내지 않는다. */
  test("남은 시간을 모르면 시각을 적지 않는다", () => {
    expect(waitLabel(null, NOW)).toBe("잠시 후 다시 물어봐 주세요.");
  });

  test("알면 언제 풀리는지 적는다", () => {
    expect(waitLabel(1725, NOW, "Asia/Seoul")).toBe("23:04부터 다시 물어볼 수 있어요.");
  });
});

/*
 * 대화 이력.
 *
 * 되묻기가 F-10의 핵심이다 — "80%까지 채우려면?" → "배터리 용량을 알려주세요"
 * → "70kWh". 이력을 안 보내면 서버는 마지막 답을 첫 질문으로 읽고 다시 되묻는다.
 * 무한히 되묻는 화면이 된다.
 */
describe("이력", () => {
  function user(text: string): AskTurn {
    return { role: "user", text };
  }
  function bot(text: string): AskTurn {
    return { role: "assistant", text, recommendation: null, missingFields: [] };
  }

  test("역할과 글만 남긴다", () => {
    expect(toHistory([user("언제 충전해?"), bot("배터리 용량을 알려주세요")])).toEqual([
      { role: "user", content: "언제 충전해?" },
      { role: "assistant", content: "배터리 용량을 알려주세요" },
    ]);
  });

  /*
   * 서버가 history[-6:]만 쓴다. 더 보내도 앞쪽은 조용히 무시되므로, 보내는
   * 것과 쓰이는 것을 같게 맞춘다 — 안 그러면 "이력을 보냈는데 왜 모르지"를
   * 디버깅하게 된다.
   */
  test("서버가 쓰는 만큼만 보낸다", () => {
    const many = Array.from({ length: 20 }, (_, i) => user(`질문 ${i}`));
    const sent = toHistory(many);
    expect(sent).toHaveLength(HISTORY_TURNS);
    expect(sent.at(-1)?.content).toBe("질문 19");
    expect(sent[0].content).toBe(`질문 ${20 - HISTORY_TURNS}`);
  });

  /* 서버가 빈 content인 턴을 버린다. 자리만 차지하고 6턴 예산을 깎는다. */
  test("빈 글은 자리를 차지하지 않는다", () => {
    expect(toHistory([user("  "), user("진짜 질문")])).toEqual([
      { role: "user", content: "진짜 질문" },
    ]);
  });

  test("아무것도 없으면 빈 배열이다", () => {
    expect(toHistory([])).toEqual([]);
  });
});

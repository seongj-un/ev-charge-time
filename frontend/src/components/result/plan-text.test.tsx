import { describe, expect, test } from "vitest";

import {
  assumptionsSentence,
  durationHours,
  planSummarySentence,
  relativeDayWord,
} from "./plan-text";

/*
 * 화면의 문장은 "오늘/내일"처럼 상대 날짜를 쓴다. 기준을 실제 현재 시각으로 잡으면
 * 테스트가 자정마다 깨지고, 심사 시연에서 미래 날짜를 넣으면 "오늘"이 사라진다.
 * 그래서 기준은 언제나 사용자가 넣은 "시작 가능 시각"의 날짜다.
 */

describe("relativeDayWord", () => {
  test("같은 날은 오늘", () => {
    expect(relativeDayWord("2026-10-07T18:00", "2026-10-07T22:00")).toBe("오늘");
  });

  test("하루 뒤는 내일", () => {
    expect(relativeDayWord("2026-10-07T18:00", "2026-10-08T01:00")).toBe("내일");
  });

  test("이틀 뒤는 모레", () => {
    expect(relativeDayWord("2026-10-07T18:00", "2026-10-09T01:00")).toBe("모레");
  });

  test("그보다 멀면 날짜를 그대로 적는다", () => {
    expect(relativeDayWord("2026-10-07T18:00", "2026-10-12T01:00")).toBe("10월 12일 (월)");
  });
});

describe("durationHours", () => {
  test("자정을 넘겨도 시간 수를 센다", () => {
    expect(durationHours("2026-10-07T22:00", "2026-10-08T01:00")).toBe(3);
  });

  test("30분 단위도 센다", () => {
    expect(durationHours("2026-10-07T22:00", "2026-10-08T01:30")).toBe(3.5);
  });
});

describe("planSummarySentence", () => {
  test("시작 때·소요 시간·완료 기한을 한 줄로 잇는다", () => {
    expect(
      planSummarySentence({
        earliestStart: "2026-10-07T18:00",
        deadline: "2026-10-08T08:00",
        start: "2026-10-07T22:00:00",
        end: "2026-10-08T01:00:00",
      }),
    ).toBe("오늘 밤 시작 · 약 3시간 · 내일 08시 전 완료");
  });

  test("아침에 시작하는 계획도 때를 맞춰 부른다", () => {
    expect(
      planSummarySentence({
        earliestStart: "2026-10-07T06:00",
        deadline: "2026-10-07T18:00",
        start: "2026-10-07T09:00:00",
        end: "2026-10-07T11:00:00",
      }),
    ).toBe("오늘 아침 시작 · 약 2시간 · 오늘 18시 전 완료");
  });
});

describe("assumptionsSentence", () => {
  test("가정을 가운뎃점으로 이어 한 줄로 만든다", () => {
    expect(assumptionsSentence(["충전 출력 일정", "연속 충전", "기본요금 제외"])).toBe(
      "계산 가정: 충전 출력 일정 · 연속 충전 · 기본요금 제외",
    );
  });

  test("가정이 없으면 빈 줄을 만들지 않는다", () => {
    expect(assumptionsSentence([])).toBeNull();
  });
});

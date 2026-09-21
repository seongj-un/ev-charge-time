import { describe, expect, test } from "vitest";

import {
  defaultForm,
  fromSearchParams,
  toRecommendRequest,
  toSavePlanRequest,
  toSearchParams,
  type RecommendForm,
} from "./recommend-params";

const FORM: RecommendForm = {
  batteryKwh: 70,
  chargerKw: 7,
  socNow: 30,
  socTarget: 60,
  earliestStart: "2026-10-07T18:00",
  deadline: "2026-10-08T08:00",
  mode: "self_low",
};

/*
 * 입력 화면과 결과 화면이 서로 다른 라우트다. 조건을 메모리에 들고 넘기면
 * 결과 화면에서 새로고침하는 순간 날아간다. URL에 실어 보내면 새로고침도,
 * 뒤로가기도, 링크 공유도 그냥 된다.
 */
describe("toSearchParams · fromSearchParams", () => {
  test("왕복해도 값이 그대로다", () => {
    expect(fromSearchParams(toSearchParams(FORM))).toEqual(FORM);
  });

  test("URL에 사람이 읽을 수 있는 이름으로 담는다", () => {
    const params = toSearchParams(FORM);
    expect(params.get("battery_kwh")).toBe("70");
    expect(params.get("soc_now")).toBe("30");
    expect(params.get("earliest_start")).toBe("2026-10-07T18:00");
    expect(params.get("mode")).toBe("self_low");
  });

  test("필수 값이 빠지면 읽지 않는다", () => {
    const params = toSearchParams(FORM);
    params.delete("battery_kwh");
    expect(fromSearchParams(params)).toBeNull();
  });

  test("숫자가 아닌 값이 오면 읽지 않는다", () => {
    const params = toSearchParams(FORM);
    params.set("charger_kw", "일곱");
    expect(fromSearchParams(params)).toBeNull();
  });

  test("모르는 충전 방식이 오면 읽지 않는다", () => {
    const params = toSearchParams(FORM);
    params.set("mode", "self_medium");
    expect(fromSearchParams(params)).toBeNull();
  });
});

describe("toRecommendRequest", () => {
  test("백엔드 요청 모양으로 바꾼다", () => {
    expect(toRecommendRequest(FORM)).toEqual({
      battery_kwh: 70,
      charger_kw: 7,
      soc_now: 30,
      soc_target: 60,
      earliest_start: "2026-10-07T18:00",
      deadline: "2026-10-08T08:00",
      mode: "self_low",
    });
  });

  test("시각은 표준시를 붙이지 않고 그대로 보낸다", () => {
    // 백엔드가 표준시 없는 입력을 KST로 읽는다 (API 명세서 1장).
    // 여기서 Z를 붙이면 9시간 어긋난 추천이 돌아온다.
    const request = toRecommendRequest(FORM);
    expect(request.earliest_start).not.toContain("Z");
    expect(request.earliest_start).not.toContain("+");
  });
});

describe("defaultForm", () => {
  test("시작 시각을 30분 단위로 올림한다", () => {
    const form = defaultForm(new Date(2026, 9, 7, 18, 12));
    expect(form.earliestStart).toBe("2026-10-07T18:30");
  });

  test("정각이면 그대로 둔다", () => {
    const form = defaultForm(new Date(2026, 9, 7, 18, 0));
    expect(form.earliestStart).toBe("2026-10-07T18:00");
  });

  test("완료 시각은 그다음 아침 8시다", () => {
    const form = defaultForm(new Date(2026, 9, 7, 18, 0));
    expect(form.deadline).toBe("2026-10-08T08:00");
  });

  test("새벽이면 완료 시각은 그날 아침 8시다", () => {
    const form = defaultForm(new Date(2026, 9, 8, 2, 0));
    expect(form.deadline).toBe("2026-10-08T08:00");
  });

  test("아침 8시를 지났으면 다음날 8시로 넘어간다", () => {
    const form = defaultForm(new Date(2026, 9, 8, 8, 30));
    expect(form.deadline).toBe("2026-10-09T08:00");
  });
});

/*
 * 차량을 골라 추천받았으면 그 사실을 저장까지 들고 가야 한다. 안 그러면
 * SavedPlan.vehicle_name이 항상 null이라 기록 화면이 "어느 차로 세운 계획인지"를
 * 영영 모른다. 그런데 추천 요청에까지 실으면 안 된다 — vehicle_id가 붙은 요청은
 * 로그인을 요구해서, 결과 URL을 공유받은 사람이 401을 맞는다.
 */
describe("vehicle_id", () => {
  const WITH_VEHICLE: RecommendForm = { ...FORM, vehicleId: "v1" };

  test("URL에 실려 왕복한다", () => {
    expect(fromSearchParams(toSearchParams(WITH_VEHICLE))).toEqual(WITH_VEHICLE);
  });

  test("차량을 안 골랐으면 URL을 더럽히지 않는다", () => {
    expect(toSearchParams(FORM).has("vehicle_id")).toBe(false);
    expect(fromSearchParams(toSearchParams(FORM))).toEqual(FORM);
  });

  test("추천 요청에는 싣지 않는다", () => {
    // 게스트가 결과 링크를 열어도 401이 나지 않아야 한다.
    expect(toRecommendRequest(WITH_VEHICLE)).not.toHaveProperty("vehicle_id");
    // 값은 이미 폼에 복사돼 있으므로 추천 결과는 똑같이 나온다.
    expect(toRecommendRequest(WITH_VEHICLE)).toEqual(toRecommendRequest(FORM));
  });

  test("저장 요청에는 싣는다", () => {
    expect(toSavePlanRequest(WITH_VEHICLE)).toMatchObject({
      vehicle_id: "v1",
      battery_kwh: 70,
    });
  });

  test("차량을 안 골랐으면 저장 요청에도 없다", () => {
    expect(toSavePlanRequest(FORM)).not.toHaveProperty("vehicle_id");
  });
});

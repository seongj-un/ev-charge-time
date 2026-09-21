import { describe, expect, test } from "vitest";

import StationsPage, { metadata } from "./page";

/*
 * 라우트는 화면을 얹기만 한다. 화면의 동작은 StationsScreen.test.tsx가 본다.
 * 여기서는 이 경로가 더 이상 "준비 중" 자리표시자가 아니라는 것만 못 박는다.
 */
describe("/stations 라우트", () => {
  test("제목을 붙인다", () => {
    expect(metadata.title).toBe("주변 충전소");
  });

  test("실제 화면을 얹는다", () => {
    expect(StationsPage().type).toBeTypeOf("function");
  });
});

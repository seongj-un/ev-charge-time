import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { toSearchParams, type RecommendForm } from "@/lib/recommend-params";

import RecommendPage from "./page";

/** 날짜·시각 칸의 현재 값 ("YYYY-MM-DDTHH:mm"). 묶음(group)이 data-value로 들고 있다. */
function readTime(label: string): string {
  return screen.getByRole("group", { name: label }).getAttribute("data-value") ?? "";
}

/*
 * 결과 화면의 "조건 고치기"는 조건 전체를 쿼리로 달고 이 화면으로 돌아온다.
 * 예전에는 이 화면이 day·mode만 읽어서, 돌아오는 순간 배터리 용량·충전량·
 * 시각이 전부 기본값으로 바뀌었다.
 */
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/components/auth/SessionProvider", () => ({
  useSession: () => ({
    status: "anonymous",
    user: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    clear: vi.fn(),
  }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

const BACK: RecommendForm = {
  batteryKwh: 64,
  chargerKw: 11,
  socNow: 15,
  socTarget: 85,
  earliestStart: "2026-11-02T21:30",
  deadline: "2026-11-03T07:00",
  mode: "self_high",
};

async function renderWith(params: Record<string, string>) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
  render(await RecommendPage({ searchParams: Promise.resolve(params) }));
}

describe("RecommendPage", () => {
  test("조건 고치기로 돌아오면 넣었던 조건을 그대로 채운다", async () => {
    await renderWith(Object.fromEntries(toSearchParams(BACK)));

    expect(screen.getByLabelText("배터리 용량")).toHaveValue("64");
    expect(screen.getByLabelText("충전기 출력")).toHaveValue("11");
    expect(screen.getByLabelText("현재 충전량")).toHaveValue("15");
    expect(screen.getByLabelText("목표 충전량")).toHaveValue("85");
    expect(readTime("충전 시작 가능")).toBe("2026-11-02T21:30");
    expect(readTime("이때까지 완료")).toBe("2026-11-03T07:00");
    expect(screen.getByRole("radio", { name: "자가 고압" })).toBeChecked();
  });

  test("하루 단가에서 넘어온 day·mode는 예전처럼 그 날짜 기본값으로 채운다", async () => {
    await renderWith({ day: "2026-10-31", mode: "self_high" });

    expect(readTime("충전 시작 가능")).toBe("2026-10-31T18:00");
    expect(readTime("이때까지 완료")).toBe("2026-11-01T08:00");
    expect(screen.getByRole("radio", { name: "자가 고압" })).toBeChecked();
    expect(screen.getByLabelText("배터리 용량")).toHaveValue("70");
  });

  test("하루 단가에서 넘어온 공용 급속 단가도 채운다", async () => {
    await renderWith({ day: "2026-10-31", mode: "public_fast", public_base_price: "347" });

    expect(screen.getByLabelText("공용 급속 단가")).toHaveValue("347");
  });
});

"""하루 시나리오 (BE-12): 차량 앱이 실제로 부르는 순서대로 하루를 따라간다.

기기 발급 → 시동 ON 브리핑 → 귀가 중 음성 브리핑(가짜 Claude) → "7시 반" → 계획(saving_id)
→ 출발 기록 → 확정 → 월 합계 → 출발 기록이 쌓인 뒤 다음 귀가 브리핑이 "내일도 오전 7시
30분" 제안. 단계마다 숫자가 앞 단계, 그리고 같은 입력의 공개 계산 API(`car/plan`)와 맞는지
본다. 시계는 고정한다(`routes.car.now_kst`). Claude는 가짜 클라이언트다.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from evcharge.api.routes import car
from evcharge.api.routes.car import anthropic_api_key, claude_client
from evcharge.domain.pricing import KST
from evcharge.infra.claude import ClaudeReply, TextPart, ToolCall

BATTERY_WH = 77_400
TUE = 17  # 2026-11-17 화요일
WED = 18
THU = 19


def kst(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=KST)


class FakeClaude:
    def __init__(self) -> None:
        self.replies: list[ClaudeReply] = []
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


class Clock:
    def __init__(self) -> None:
        self.now = kst(TUE, 8, 0)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    instance = Clock()
    monkeypatch.setattr(car, "now_kst", instance)
    return instance


@pytest.fixture
def fake(client) -> FakeClaude:
    instance = FakeClaude()
    client.app.dependency_overrides[anthropic_api_key] = lambda: "test-key"
    client.app.dependency_overrides[claude_client] = lambda: instance
    return instance


def plan(client, **body) -> dict:
    """같은 입력의 공개 계산 API(토큰 없음). 각 단계의 숫자를 이것과 맞춰 본다."""
    response = client.post("/api/car/plan", json={"battery_capacity_wh": BATTERY_WH, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_day_with_the_car_app(client, clock, fake):
    # ── 1. 설치: 기기 토큰 발급 (화 08:00) ─────────────────────────────────
    response = client.post("/api/car/devices")
    assert response.status_code == 201
    headers = {"Authorization": f"Bearer {response.json()['device_token']}"}

    # ── 2. 시동 ON 브리핑 (화 17:50, 잔량 32%) ─────────────────────────────
    clock.now = kst(TUE, 17, 50)
    brief = client.post(
        "/api/car/briefing",
        json={"soc_now": 32, "battery_capacity_wh": BATTERY_WH},
        headers=headers,
    ).json()
    tonight = brief["tonight"]
    assert tonight["needs_charging"] is True
    # 평소 출발 기록이 없으니 기본 가정(다음 08:00)이고, 꽂는 시각은 18:00으로 가정한다.
    assert tonight["depart_basis"] == "default"
    assert tonight["depart_at"] == "2026-11-18T08:00:00+09:00"
    same = plan(
        client, soc_now=32, plug_in_at="2026-11-17T18:00", depart_at="2026-11-18T08:00"
    )
    assert tonight["reservation"] == same["reservation"]
    assert tonight["savings_won"] == same["savings_won"] > 0
    assert f"약 {same['savings_won']:,}원 아껴요" in brief["speech"]
    assert brief["saving_id"] is not None  # 브리핑 대기 기록(기기당 하나)

    # ── 3. 귀가 중 음성 브리핑 (화 18:20, 도착 18:40에 25% 예상) ──────────
    clock.now = kst(TUE, 18, 20)
    context = {
        "soc_now": 30,
        "battery_capacity_wh": BATTERY_WH,
        "arrival_soc": 25,
        "arrival_at": "2026-11-17T18:40",
    }
    arrival = client.post(
        "/api/car/voice",
        json={"trigger": "arrival_briefing", "context": context},
        headers=headers,
    ).json()
    question = "내일 몇 시에 출발하세요?"
    assert arrival["speech"] == f"집에 도착하면 배터리가 25% 남아요. {question}"
    assert arrival["actions"] == [{"type": "ask", "question": question}]
    assert fake.calls == []  # 첫 질문은 서버 문장이라 Claude를 부르지 않는다

    # ── 4. 운전자 "7시 반" → 계획과 예약 값 (가짜 Claude가 plan_charge를 부른다) ──
    fake.replies = [
        ClaudeReply(
            stop_reason="tool_use",
            parts=[ToolCall(id="t1", name="plan_charge", input={"depart_time": "07:30"})],
        ),
        ClaudeReply(stop_reason="end_turn", parts=[TextPart(text="예약해 두었어요.")]),
    ]
    voice = client.post(
        "/api/car/voice",
        json={
            "text": "7시 반에 나가",
            "history": [{"role": "wattit", "text": arrival["speech"]}],
            "context": context,
        },
        headers=headers,
    ).json()
    # 꽂는 시각은 도착 예정 18:40, 시작 잔량은 도착 예상 25%, 출발은 그 뒤 처음 오는 07:30
    expected = plan(
        client, soc_now=25, plug_in_at="2026-11-17T18:40", depart_at="2026-11-18T07:30"
    )
    reservation = expected["reservation"]
    assert voice["actions"] == [
        {
            "type": "set_reservation",
            "start_hhmm": reservation["start_hhmm"],
            "end_hhmm": reservation["end_hhmm"],
        }
    ]
    assert voice["fallback"] is False
    plan_saving_id = voice["saving_id"]
    assert plan_saving_id is not None
    plan_savings = expected["savings_won"]
    assert plan_savings > 0
    # Claude가 받은 도구 결과의 숫자도 같은 계산값이다(이 값만 말할 수 있다)
    tool_result = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert tool_result["savings_won"] == plan_savings
    assert tool_result["reservation"] == {
        "start": reservation["start_hhmm"],
        "end": reservation["end_hhmm"],
    }
    assert (tool_result["soc_start"], tool_result["depart_at"]) == (25, "2026-11-18 07:30")

    # 운전자가 말한 07:30은 출발 학습에 "말한 시각"으로 남는다(그 날 이후의 제안 근거)
    suggest = client.get("/api/car/departures/suggest?date=2026-11-19", headers=headers).json()
    assert suggest["basis_count"] == 1
    assert suggest["confidence"] is None  # 1건으로는 제안하지 않는다

    # ── 5. 다음 날 출발(기어 P 해제) 기록 (수 07:31) ─────────────────────────
    clock.now = kst(WED, 7, 31)
    departed = client.post(
        "/api/car/departures", json={"departed_at": "2026-11-18T07:31"}, headers=headers
    )
    assert departed.status_code == 200  # 30분 안의 "말한 07:30"을 실제 출발로 바꾼다
    assert departed.json()["merged"] is True
    assert departed.json()["source"] == "observed"

    # ── 6. 예약 충전이 돌았음을 확인하고 절감 확정 (수 08:00) ────────────────
    clock.now = kst(WED, 8, 0)
    confirmed = client.post(f"/api/car/savings/{plan_saving_id}/confirm", headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["savings_won"] == plan_savings
    assert confirmed.json()["source"] == "plan"

    summary = client.get("/api/car/savings/summary?month=2026-11", headers=headers).json()
    # 확정한 것만 센다. 브리핑 대기 기록은 확정하지 않았으니 빠진다.
    assert (summary["month_won"], summary["month_count"]) == (plan_savings, 1)
    assert summary["year_won"] == summary["total_won"] == plan_savings
    assert f"{plan_savings:,}원" in summary["speech"]

    # ── 7. 지난주 평일 출발 기록 4건 더 (앱이 쌓아 둔 것을 보낸다) ─────────
    clock.now = kst(WED, 8, 5)
    for departed_at in (
        "2026-11-10T07:28",
        "2026-11-11T07:33",
        "2026-11-12T07:30",
        "2026-11-13T07:29",
    ):
        response = client.post(
            "/api/car/departures", json={"departed_at": departed_at}, headers=headers
        )
        assert response.status_code == 201, response.text
    suggest = client.get("/api/car/departures/suggest?date=2026-11-19", headers=headers).json()
    # 07:28, 07:29, 07:30, 07:31, 07:33의 중앙값 07:30, 실제 출발 5건이라 high
    assert suggest["suggested_depart_at"] == "2026-11-19T07:30:00+09:00"
    assert (suggest["confidence"], suggest["basis_count"]) == ("high", 5)

    # ── 8. 다음 시동 ON 브리핑은 평소 출발 07:30 기준 (수 17:50) ─────────────
    clock.now = kst(WED, 17, 50)
    brief = client.post(
        "/api/car/briefing",
        json={"soc_now": 32, "battery_capacity_wh": BATTERY_WH},
        headers=headers,
    ).json()
    tonight = brief["tonight"]
    assert tonight["depart_basis"] == "usual"
    assert tonight["depart_at"] == "2026-11-19T07:30:00+09:00"
    same = plan(
        client, soc_now=32, plug_in_at="2026-11-18T18:00", depart_at="2026-11-19T07:30"
    )
    assert tonight["reservation"] == same["reservation"]
    assert tonight["savings_won"] == same["savings_won"]
    assert brief["savings"]["month_won"] == plan_savings  # 브리핑의 이번 달 절약 = 합계

    # ── 9. 다음 귀가 브리핑은 평소 시각을 묻는다 (수 18:20) ──────────────────
    clock.now = kst(WED, 18, 20)
    context = {**context, "arrival_at": "2026-11-18T18:40"}
    arrival = client.post(
        "/api/car/voice",
        json={"trigger": "arrival_briefing", "context": context},
        headers=headers,
    ).json()
    assert arrival["speech"] == (
        "집에 도착하면 배터리가 25% 남아요. 내일도 오전 7시 30분에 출발하세요?"
    )

    # ── 10. "응" → 평소 시각으로 계획 (Claude는 07:30을 넣는다) ─────────────
    fake.replies = [
        ClaudeReply(
            stop_reason="tool_use",
            parts=[ToolCall(id="t2", name="plan_charge", input={"depart_time": "07:30"})],
        ),
        ClaudeReply(stop_reason="end_turn", parts=[TextPart(text="평소처럼 예약해 두었어요.")]),
    ]
    voice = client.post(
        "/api/car/voice",
        json={
            "text": "응",
            "history": [{"role": "wattit", "text": arrival["speech"]}],
            "context": context,
        },
        headers=headers,
    ).json()
    expected = plan(
        client, soc_now=25, plug_in_at="2026-11-18T18:40", depart_at="2026-11-19T07:30"
    )
    assert voice["actions"] == [
        {
            "type": "set_reservation",
            "start_hhmm": expected["reservation"]["start_hhmm"],
            "end_hhmm": expected["reservation"]["end_hhmm"],
        }
    ]
    # 평소 시각 질문에 "응"이라고 한 07:30은 말한 시각으로 남지만(목요일), 실제 출발이 3건
    # 이상이면 제안은 실제 출발만 센다.
    suggest = client.get("/api/car/departures/suggest?date=2026-11-20", headers=headers).json()
    assert suggest["suggested_depart_at"] == "2026-11-20T07:30:00+09:00"
    assert (suggest["confidence"], suggest["basis_count"]) == ("high", 5)

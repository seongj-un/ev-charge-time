"""차량 기본 예약 충전에 넣을 시작·종료 시각 (차량 앱 BE-1).

서버는 충전을 직접 켜고 끄지 않는다. 계산한 최저 비용 구간을 운전자가 차량의
예약 충전 화면에 그대로 넣을 수 있는 분 단위 시각으로 바꿔 줄 뿐이다.

차량 예약 충전은 분 단위(HH:MM)만 받는데, 계산 결과(``planner``)에는 초가
붙을 수 있다 (꽂는 시각이 "지금"이거나, 출발 시각에서 거꾸로 잰 가장 늦은
시작). 그래서 두 가지를 지킨다.

- 시작은 꽂는 시각보다 앞설 수 없다. 분 단위로 내려도 꽂는 시각 이후면 내리고,
  아니면 올린다.
- 종료는 분 단위로 올린다. 충전이 덜 되면 안 되므로, 올린 시작에서 필요한 충전
  시간을 다 채운 시각보다도 앞서지 않게 한다.
- 다만 종료는 출발 시각을 넘지 않는다. 꽂는 시각과 출발 시각 사이가 충전 시간과
  거의 같을 때(초가 붙은 꽂는 시각) 시작을 올리면 종료가 출발 뒤로 밀리는데, 그때는
  종료를 출발 시각(분 단위 내림)에 맞춘다. 이 경우에만 예약 구간이 충전 시간보다
  2분 미만 짧을 수 있다. 맞춘 구간이 비면(충전이 1분 남짓이라 시작과 종료가 같은
  분에 걸림) 예약으로 나타낼 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

_MINUTE = timedelta(minutes=1)

# 차량 예약 충전은 하루 안의 시작·종료 시각(HH:MM)만 받는다. 24시간 이상 걸리는
# 충전은 시작과 종료가 같은 HH:MM이 되거나 하루를 건너뛰어 한 번의 예약으로
# 나타낼 수 없다.
MAX_RESERVATION_SPAN = timedelta(hours=24)


@dataclass(frozen=True)
class Reservation:
    start_at: datetime
    end_at: datetime

    @property
    def start_hhmm(self) -> str:
        return self.start_at.strftime("%H:%M")

    @property
    def end_hhmm(self) -> str:
        return self.end_at.strftime("%H:%M")


def floor_minute(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def ceil_minute(moment: datetime) -> datetime:
    floor = floor_minute(moment)
    return moment if floor == moment else floor + _MINUTE


def round_window(
    start: datetime, end: datetime, plug_in_at: datetime, *, deadline: datetime
) -> tuple[datetime, datetime]:
    """계산된 충전 구간 ``[start, end)``를 분 단위로 맞춘다 (머리말의 규칙).

    ``plug_in_at <= start < end <= deadline``이어야 한다 (``planner``가 보장한다).
    시각은 받은 그대로의 시간대로 돌려준다 — 호출자가 KST로 넘긴다. 맞춘 구간이 빌
    수 있다(``end <= start``) — ``build_reservation``이 걸러 낸다.
    """
    duration = end - start
    rounded_start = floor_minute(start)
    if rounded_start < plug_in_at:
        rounded_start = ceil_minute(start)
    rounded_end = min(ceil_minute(max(end, rounded_start + duration)), floor_minute(deadline))
    return rounded_start, rounded_end


def build_reservation(
    start: datetime, end: datetime, plug_in_at: datetime, *, deadline: datetime
) -> Reservation | None:
    """``round_window``로 맞춘 구간을 예약 값으로.

    구간이 비었거나 24시간 이상이면 한 번의 예약으로 넣을 수 없어 ``None``이다.
    """
    rounded_start, rounded_end = round_window(start, end, plug_in_at, deadline=deadline)
    if rounded_end <= rounded_start or rounded_end - rounded_start >= MAX_RESERVATION_SPAN:
        return None
    return Reservation(start_at=rounded_start, end_at=rounded_end)

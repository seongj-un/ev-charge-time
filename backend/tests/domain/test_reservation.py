from datetime import datetime, timedelta

from evcharge.domain.pricing import KST
from evcharge.domain.reservation import (
    MAX_RESERVATION_SPAN,
    build_reservation,
    ceil_minute,
    floor_minute,
    round_window,
)


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


def test_minute_aligned_window_is_kept():
    reservation = build_reservation(kst(2026, 10, 7, 22), kst(2026, 10, 8, 1), kst(2026, 10, 7, 18))

    assert reservation is not None
    assert reservation.start_at == kst(2026, 10, 7, 22)
    assert reservation.end_at == kst(2026, 10, 8, 1)


def test_window_across_midnight_gives_next_day_end_and_clock_values():
    reservation = build_reservation(
        kst(2026, 10, 7, 23, 30), kst(2026, 10, 8, 5, 45), kst(2026, 10, 7, 18)
    )

    assert reservation is not None
    assert reservation.start_hhmm == "23:30"
    assert reservation.end_hhmm == "05:45"
    assert reservation.end_at.date() == datetime(2026, 10, 8).date()


def test_end_seconds_are_rounded_up_to_the_next_minute():
    reservation = build_reservation(
        kst(2026, 10, 7, 22), kst(2026, 10, 8, 1, 0, 36), kst(2026, 10, 7, 18)
    )

    assert reservation is not None
    assert reservation.end_at == kst(2026, 10, 8, 1, 1)
    assert reservation.end_hhmm == "01:01"


def test_start_is_floored_when_that_stays_after_plug_in():
    # 출발 시각에서 거꾸로 잰 가장 늦은 시작처럼 초가 붙은 시작.
    start = kst(2026, 10, 8, 4, 59, 24)
    end = kst(2026, 10, 8, 8)
    reservation = build_reservation(start, end, kst(2026, 10, 7, 18))

    assert reservation is not None
    assert reservation.start_at == kst(2026, 10, 8, 4, 59)
    assert reservation.end_at == kst(2026, 10, 8, 8)


def test_start_is_never_before_plug_in():
    # 서버 현재 시각을 꽂는 시각으로 쓰면 초가 붙는다. 내리면 꽂기 전이 된다.
    plug_in = kst(2026, 10, 7, 18, 3, 27)
    duration = timedelta(hours=2, minutes=59, seconds=50)
    reservation = build_reservation(plug_in, plug_in + duration, plug_in)

    assert reservation is not None
    assert reservation.start_at == kst(2026, 10, 7, 18, 4)
    assert reservation.start_at >= plug_in
    # 올린 시작에서도 필요한 충전 시간을 다 채운다.
    assert reservation.end_at - reservation.start_at >= duration
    assert reservation.end_at == kst(2026, 10, 7, 21, 4)


def test_rounded_window_always_covers_the_charge_duration():
    plug_in = kst(2026, 10, 7, 18, 0, 59)
    for seconds in (1, 29, 30, 59, 61, 3599):
        start = plug_in + timedelta(seconds=seconds)
        duration = timedelta(hours=3, seconds=seconds * 7)
        rounded_start, rounded_end = round_window(start, start + duration, plug_in)

        assert rounded_start >= plug_in
        assert rounded_start.second == rounded_end.second == 0
        assert rounded_end - rounded_start >= duration
        assert rounded_end >= start + duration


def test_window_of_a_day_or_more_cannot_be_one_reservation():
    start = kst(2026, 10, 7, 22)

    assert build_reservation(start, start + MAX_RESERVATION_SPAN, start) is None
    assert build_reservation(start, start + timedelta(hours=23, minutes=59), start) is not None


def test_floor_and_ceil_minute():
    moment = kst(2026, 10, 7, 22, 15, 1)

    assert floor_minute(moment) == kst(2026, 10, 7, 22, 15)
    assert ceil_minute(moment) == kst(2026, 10, 7, 22, 16)
    assert ceil_minute(kst(2026, 10, 7, 22, 15)) == kst(2026, 10, 7, 22, 15)

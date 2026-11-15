"""공공 API 글 정리 (BE-14): 제어(Cc)·서식(Cf) 문자를 빼고 공백을 편다."""

from __future__ import annotations

import pytest

from evcharge.api.car_route_service import MAX_ADDRESS, short_name, station_address
from evcharge.api.car_voice_service import external_text
from evcharge.domain.public_text import clean_public_text


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("유성구\x00충전소", "유성구충전소"),  # NUL (Cc)
        ("\u202e소전충 람가빛", "소전충 람가빛"),  # RIGHT-TO-LEFT OVERRIDE (Cf)
        ("유성구\u200b충전소", "유성구충전소"),  # ZERO WIDTH SPACE (Cf)
        ("유성구 \u2066충전소\u2069", "유성구 충전소"),  # 방향 격리 (Cf)
        ("유성구 \u200b 충전소", "유성구 충전소"),  # 뺀 자리에 공백이 겹치지 않는다
        ("광주광역시 남구\n대촌로\t7", "광주광역시 남구 대촌로 7"),  # 줄바꿈·탭은 공백으로
        ("서울 강남구 테헤란로 1", "서울 강남구 테헤란로 1"),  # 한글은 그대로
        (
            "\u1112\u1161\u11ab\u1100\u1173\u11af",
            "\u1112\u1161\u11ab\u1100\u1173\u11af",
        ),  # 첫가끝 자모(Lo)
        ("충전소 \U0001f50c\u26a1", "충전소 \U0001f50c\u26a1"),  # 이모지(So)는 남는다
        ("cafe\u0301", "cafe\u0301"),  # 결합 문자(Mn)는 남는다
    ],
)
def test_clean_public_text(raw, cleaned):
    assert clean_public_text(raw) == cleaned


@pytest.mark.parametrize("raw", [None, "", "  ", "\x00\u202e\u200b", "\n\u200b\t"])
def test_nothing_left_is_empty_and_the_address_is_null(raw):
    assert clean_public_text(raw) == ""
    assert station_address({"address": raw}) is None
    assert short_name(raw) == ""


def test_every_name_and_address_helper_strips_control_and_format_chars():
    raw = "\u202e유성구\x00 충전소\u200b"
    assert short_name(raw) == "유성구 충전소"
    assert external_text(raw) == "유성구 충전소"
    assert station_address({"address": raw}) == "유성구 충전소"
    # 길이는 정리한 뒤에 자른다: 서식 문자가 길이를 차지하지 않는다
    assert station_address({"address": "\u200b" * 50 + "가" * 250}) == "가" * MAX_ADDRESS

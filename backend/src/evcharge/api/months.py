"""KST 달·해 경계. ``/api/me/plans``(F-13)와 ``/api/car/savings/summary``(와트잇 BE-5)가 함께 쓴다.

두 곳이 같은 함수를 써야 "10월"이 가리키는 구간이 화면마다 갈리지 않는다.
"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import HTTPException

from ..domain.pricing import KST

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
# 다음 달·다음 해 경계(``year + 1``)를 만들 수 있는 마지막 해. 9999년이면 datetime이
# 10000년을 만들지 못해 500이 났다.
MAX_YEAR = 9998
_MONTH_ERROR = "month는 YYYY-MM 형식이어야 합니다."


def month_bounds(month: str) -> tuple[datetime, datetime]:
    """``"YYYY-MM"``을 KST 기준 [그 달 1일 00:00, 다음 달 1일 00:00) 경계로.

    (B-3) 예전에는 형식 검증이 없어 ``"26-10"``이나 ``"2026-2"``도 조용히
    받아 ``month``를 그대로 응답에 되돌려줬다. ``int()``/범위 체크만으로는
    자릿수가 다른 값을 걸러내지 못해 ``YYYY-MM`` 정규식으로 먼저 형식 자체를
    확인한다.
    """
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail=_MONTH_ERROR)
    try:
        year_str, month_str = month.split("-")
        year, month_num = int(year_str), int(month_str)
        if not 1 <= year <= MAX_YEAR or not 1 <= month_num <= 12:
            raise ValueError(month)
        start = datetime(year, month_num, 1, tzinfo=KST)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_MONTH_ERROR) from exc

    if month_num == 12:
        end = datetime(year + 1, 1, 1, tzinfo=KST)
    else:
        end = datetime(year, month_num + 1, 1, tzinfo=KST)

    return start, end


def year_bounds(year: int) -> tuple[datetime, datetime]:
    """KST 기준 [그해 1월 1일 00:00, 다음 해 1월 1일 00:00)."""
    return datetime(year, 1, 1, tzinfo=KST), datetime(year + 1, 1, 1, tzinfo=KST)


def month_of(moment: datetime) -> str:
    """KST로 본 ``"YYYY-MM"``."""
    local = moment.astimezone(KST)
    return f"{local.year:04d}-{local.month:02d}"

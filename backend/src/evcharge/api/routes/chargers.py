"""F-07 주변 충전소.

**이 라우터는 공공 API를 부르지 않는다.** 개발계정 트래픽이 하루 1,000건이라
사용자 요청마다 부르면 즉시 넘친다. 전 사용자 공유 캐시(``charger_cache``)만
읽고, 캐시는 수집기(``python -m evcharge.sync``)가 채운다.

반경 조회는 두 단계다: 인덱스를 타는 바운딩 박스로 DB에서 후보를 좁히고,
정확한 하버사인 거리는 그 후보에 대해서만 계산한다. 32,835건을 파이썬으로
끌어오지 않기 위한 것이고, 그래서 ``charger_cache``에 ``lat``/``lng`` 컬럼과
복합 인덱스가 있다.

사용자의 ``lat``/``lng``는 조회에만 쓰고 저장하지 않는다 (명세).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...domain.geo import bounding_box, haversine_m
from ...infra.db import get_session
from ...infra.models import ChargerCache, FavoriteStation, User
from ...settings import get_settings
from ..auth_deps import optional_user
from ..schemas import MAX_CHARGER_KW, ChargerOut, StationOut

router = APIRouter(prefix="/api", tags=["chargers"])

# 인증 없이 닿는 경로라 상한을 둔다(I-4와 같은 이유). 20km면 나주·광주 전역을
# 덮고도 남는다. 상한이 없으면 반경 하나로 캐시 전체를 파이썬으로 끌어올 수 있다.
MAX_RADIUS_M = 20_000
DEFAULT_RADIUS_M = 2_000

# 공공 API 충전기 상태 코드(stat) 중 "충전대기" = 지금 꽂을 수 있음. 활용가이드의
# 다른 코드(통신이상·충전중·운영중지·점검중·상태미확인)는 비어 있다고 보지 않는다.
STATUS_AVAILABLE = "2"


def charger_api_key() -> str:
    """설정의 공공 API 키.

    의존성으로 빼 둔 이유는 테스트가 ``dependency_overrides``로 "키 있음/없음"을
    직접 정할 수 있게 하기 위해서다 — 개발자 ``.env``에 키가 있느냐에 따라
    테스트 결과가 갈리면 안 된다.
    """
    return get_settings().charger_api_key


@router.get("/chargers", response_model=list[StationOut])
def list_chargers(
    lat: float = Query(ge=-90, le=90, description="위도. 조회에만 쓰고 저장하지 않는다"),
    lng: float = Query(ge=-180, le=180, description="경도. 조회에만 쓰고 저장하지 않는다"),
    radius_m: int = Query(DEFAULT_RADIUS_M, gt=0, le=MAX_RADIUS_M),
    charger_type: str | None = Query(
        None,
        max_length=32,
        description=(
            "충전기 종류 코드. 공공 API의 chgerType 값을 그대로 쓴다 "
            "(추정 매핑을 넣지 않는다). 한 대라도 맞으면 그 충전소를 남긴다."
        ),
    ),
    available_only: bool = Query(
        False,
        description=(
            "true면 상태 코드 2(충전대기)인 충전기가 한 대 이상 있는 충전소만 남긴다. "
            "남긴 충전소의 충전기 목록은 전부 보여 준다."
        ),
    ),
    min_kw: float | None = Query(
        None,
        gt=0,
        le=MAX_CHARGER_KW,
        allow_inf_nan=False,
        description=(
            "이 출력(kW) 이상인 충전기가 한 대 이상 있는 충전소만 남긴다. "
            "available_only와 함께 주면 같은 충전기가 두 조건을 다 맞아야 한다."
        ),
    ),
    api_key: str = Depends(charger_api_key),
    user: User | None = Depends(optional_user),
    session: DbSession = Depends(get_session),
) -> list[StationOut]:
    if not api_key:
        # 키가 없으면 캐시를 채울 방법 자체가 없다. settings.py가 약속한 대로
        # 501을 유지한다 — 프론트가 "아직 열리지 않았어요"로 안내한다.
        raise HTTPException(
            status_code=501,
            detail="주변 충전소 조회는 아직 준비되지 않았습니다. (충전소 API 인증키 미설정)",
        )

    min_lat, min_lng, max_lat, max_lng = bounding_box(lat, lng, radius_m)
    # 1차 필터: 인덱스를 타는 범위 비교. 좌표가 없는 행(NULL)은 여기서 빠진다.
    candidates = session.scalars(
        select(ChargerCache).where(
            ChargerCache.lat.between(min_lat, max_lat),
            ChargerCache.lng.between(min_lng, max_lng),
        )
    ).all()

    wanted = _ChargerFilter(
        charger_type=charger_type.strip().lower() if charger_type else None,
        available_only=available_only,
        min_kw=min_kw,
    )
    found: list[tuple[float, ChargerCache]] = []
    for row in candidates:
        # 2차 필터: 박스는 원보다 크다(모서리). 정확한 거리로 한 번 더 거른다.
        distance = haversine_m(lat, lng, row.lat, row.lng)
        if distance > radius_m:
            continue
        if wanted.is_set() and not _has_matching_charger(row, wanted):
            continue
        found.append((distance, row))

    if not found and _cache_is_empty(session):
        # "주변에 충전소가 없다"와 "아직 수집하지 않았다"는 다른 말이다. 빈
        # 목록으로 답하면 화면이 나주에 충전소가 없다고 말하게 된다.
        raise HTTPException(
            status_code=503,
            detail=(
                "충전소 정보를 아직 수집하지 않았습니다. "
                "잠시 후 다시 시도해 주세요."
            ),
        )

    found.sort(key=lambda item: item[0])
    favorites = _favorite_ids(session, user, [row.station_id for _, row in found])

    return [
        _to_station_out(row, distance, favorites if user is not None else None)
        for distance, row in found
    ]


@dataclass(frozen=True)
class _ChargerFilter:
    """충전기 한 대에 거는 조건들. 주지 않은 조건은 검사하지 않는다."""

    charger_type: str | None
    available_only: bool
    min_kw: float | None

    def is_set(self) -> bool:
        # 조건이 하나도 없으면 거르지 않는다 — 충전기가 0대인 충전소도 지금처럼 남는다.
        return self.charger_type is not None or self.available_only or self.min_kw is not None

    def matches(self, charger: dict) -> bool:
        if (
            self.charger_type is not None
            and str(charger.get("type", "")).strip().lower() != self.charger_type
        ):
            return False
        if self.available_only and str(charger.get("status", "")).strip() != STATUS_AVAILABLE:
            return False
        if self.min_kw is not None:
            capacity = _as_kw(charger.get("capacity_kw"))
            if capacity is None or capacity < self.min_kw:
                return False
        return True


def _has_matching_charger(row: ChargerCache, wanted: _ChargerFilter) -> bool:
    """주어진 조건을 **같은 충전기 한 대가** 모두 맞으면 그 충전소를 남긴다.

    걸러내는 단위는 충전기가 아니라 충전소다 — 조건에 맞는 충전기가 있는
    충전소를 찾는 화면이므로, 그 충전소의 나머지 충전기도 함께 보여준다.
    조건을 충전기마다 따로 보면 "7kW 충전대기 + 100kW 충전중" 충전소가
    "100kW 이상 빈 충전기" 조건에 걸려, 차 안에서 헛걸음하게 된다.
    """
    return any(wanted.matches(charger) for charger in _chargers(row))


def _as_kw(value: object) -> float | None:
    """캐시의 출력 값. 숫자가 아니거나 NaN이면 조건을 못 맞춘 것으로 본다."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        kw = float(value)
    except ValueError:
        return None
    return kw if math.isfinite(kw) else None


def _chargers(row: ChargerCache) -> list[dict]:
    chargers = (row.data or {}).get("chargers")
    return chargers if isinstance(chargers, list) else []


def _cache_is_empty(session: DbSession) -> bool:
    """수집기가 채운 행이 하나라도 있는지. 좌표 없는 행은 세지 않는다 —
    F-14가 즐겨찾기만으로 만든 행은 "수집됨"이 아니다."""
    return (
        session.scalar(
            select(ChargerCache.station_id).where(ChargerCache.lat.is_not(None)).limit(1)
        )
        is None
    )


def _favorite_ids(
    session: DbSession, user: User | None, station_ids: list[str]
) -> set[str]:
    if user is None or not station_ids:
        return set()
    return set(
        session.scalars(
            select(FavoriteStation.station_id).where(
                FavoriteStation.user_id == user.id,
                FavoriteStation.station_id.in_(station_ids),
            )
        )
    )


def _to_station_out(
    row: ChargerCache, distance_m: float, favorites: set[str] | None
) -> StationOut:
    """캐시 행 → 응답.

    문자열 필드에 ``or ""``를 두는 이유: ``StationOut``의 캐시 유래 필드는 전부
    필수라, 수집기를 거치지 않고 만들어진 행(테스트 픽스처 등)이 섞이면 응답
    검증이 500으로 터진다. 빈 문자열로 내보내면 화면이 그 사실을 드러낸다.
    """
    data = row.data or {}
    return StationOut(
        station_id=row.station_id,
        name=str(data.get("name") or ""),
        address=str(data.get("address") or ""),
        lat=row.lat,
        lng=row.lng,
        distance_m=round(distance_m),
        operator=str(data.get("operator") or ""),
        available_hours=str(data.get("available_hours") or ""),
        # 게스트는 null (명세 2-4). false로 내보내면 "즐겨찾기 안 함"이라는
        # 다른 뜻이 된다.
        is_favorite=(row.station_id in favorites) if favorites is not None else None,
        chargers=[ChargerOut(**charger) for charger in _chargers(row)],
    )

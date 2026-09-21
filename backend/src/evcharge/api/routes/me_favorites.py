"""F-14 즐겨찾는 충전소.

저장은 ``station_id``만 (infra/models.py의 FavoriteStation). 목록에 보여줄
이름·주소 등은 전 사용자 공유 캐시인 ``charger_cache``(F-07이 채움)에서
읽는다. 즐겨찾기 자체는 station_id만으로 유효하므로, 캐시에 아직 없는
station_id도 station_id만 채운 채 목록에 나온다.

``me.py``가 아니라 별도 파일인 이유: 다른 에이전트가 ``me.py``의 나머지
엔드포인트(차량·충전 기록 등)를 동시에 수정 중이라 충돌을 피하기 위함.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ...infra.db import get_session
from ...infra.models import ChargerCache, FavoriteStation, User
from ..auth_deps import current_user
from ..schemas import StationOut

router = APIRouter(prefix="/api/me/favorites", tags=["me"])

# 모두 로그인 필요. 본인 즐겨찾기만 보이며, 다른 사용자의 것은 절대 섞이지 않는다.


def _to_station_out(station_id: str, cache: ChargerCache | None) -> StationOut:
    """캐시가 있으면 이름·주소 등을 채우고, 없으면 station_id만 채운다."""
    if cache is None:
        return StationOut(station_id=station_id, is_favorite=True)

    data = cache.data
    return StationOut(
        station_id=station_id,
        name=data.get("name"),
        address=data.get("address"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        distance_m=data.get("distance_m"),
        operator=data.get("operator"),
        available_hours=data.get("available_hours"),
        is_favorite=True,
        chargers=data.get("chargers", []),
    )


@router.get("", response_model=list[StationOut])
def list_favorites(
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> list[StationOut]:
    favorites = session.scalars(
        select(FavoriteStation)
        .where(FavoriteStation.user_id == user.id)
        .order_by(FavoriteStation.created_at)
    ).all()

    station_ids = [favorite.station_id for favorite in favorites]
    caches: dict[str, ChargerCache] = {}
    if station_ids:
        caches = {
            cache.station_id: cache
            for cache in session.scalars(
                select(ChargerCache).where(ChargerCache.station_id.in_(station_ids))
            )
        }

    return [
        _to_station_out(favorite.station_id, caches.get(favorite.station_id))
        for favorite in favorites
    ]


@router.put("/{station_id}", status_code=204)
def add_favorite(
    station_id: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> None:
    """멱등: 이미 즐겨찾기한 station_id를 다시 PUT해도 204이며 중복 저장되지 않는다."""
    existing = session.scalar(
        select(FavoriteStation).where(
            FavoriteStation.user_id == user.id,
            FavoriteStation.station_id == station_id,
        )
    )
    if existing is None:
        session.add(FavoriteStation(user_id=user.id, station_id=station_id))
        session.commit()


@router.delete("/{station_id}", status_code=204)
def remove_favorite(
    station_id: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> None:
    """즐겨찾기하지 않은 station_id를 지워도 204."""
    existing = session.scalar(
        select(FavoriteStation).where(
            FavoriteStation.user_id == user.id,
            FavoriteStation.station_id == station_id,
        )
    )
    if existing is not None:
        session.delete(existing)
        session.commit()

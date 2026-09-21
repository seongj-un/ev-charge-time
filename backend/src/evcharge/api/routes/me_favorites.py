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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from ...infra.db import get_session
from ...infra.models import ChargerCache, FavoriteStation, User
from ..auth_deps import current_user
from ..schemas import FavoriteStationOut

router = APIRouter(prefix="/api/me/favorites", tags=["me"])

# 모두 로그인 필요. 본인 즐겨찾기만 보이며, 다른 사용자의 것은 절대 섞이지 않는다.


def _to_favorite_out(station_id: str, cache: ChargerCache | None) -> FavoriteStationOut:
    """캐시가 있으면 이름·주소 등을 채우고, 없으면 station_id만 채운다(나머지는 None)."""
    if cache is None:
        return FavoriteStationOut(station_id=station_id, is_favorite=True)

    data = cache.data
    return FavoriteStationOut(
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


@router.get("", response_model=list[FavoriteStationOut])
def list_favorites(
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> list[FavoriteStationOut]:
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
        _to_favorite_out(favorite.station_id, caches.get(favorite.station_id))
        for favorite in favorites
    ]


@router.put("/{station_id}", status_code=204)
def add_favorite(
    station_id: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> None:
    """멱등: 이미 즐겨찾기한 station_id를 다시 PUT해도 204이며 중복 저장되지 않는다.

    (B-2) check-then-insert(SELECT 후 없으면 INSERT)였을 때는 동시 요청 두
    건이 모두 SELECT를 통과하면 두 번째 INSERT가 복합 PK 위반으로
    IntegrityError를 냈다 — "멱등 PUT은 절대 500/에러를 내면 안 된다"는
    계약 위반이었고 리뷰어가 두 세션으로 실제 재현했다. ``ON CONFLICT DO
    NOTHING``으로 바꿔 그 경쟁 자체를 Postgres가 원자적으로 처리하게 한다.
    (A-1의 IntegrityError 안전망이 있다고 해도 이 경로는 409로 새는 것도
    틀렸다 — 멱등 API는 경쟁 중에도 항상 204여야 한다.)
    """
    stmt = (
        pg_insert(FavoriteStation)
        .values(user_id=user.id, station_id=station_id)
        .on_conflict_do_nothing(
            index_elements=[FavoriteStation.user_id, FavoriteStation.station_id]
        )
    )
    session.execute(stmt)
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

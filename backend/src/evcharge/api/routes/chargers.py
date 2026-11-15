"""F-07 주변 충전소.

**이 라우터는 공공 API를 부르지 않는다.** 개발계정 트래픽이 하루 1,000건이라
사용자 요청마다 부르면 즉시 넘친다. 전 사용자 공유 캐시(``charger_cache``)만
읽고, 캐시는 수집기(``python -m evcharge.sync``)가 채운다.

반경 조회는 두 단계다: 인덱스를 타는 바운딩 박스로 DB에서 후보를 좁히고,
정확한 하버사인 거리는 그 후보에 대해서만 계산한다. 32,835건을 파이썬으로
끌어오지 않기 위한 것이고, 그래서 ``charger_cache``에 ``lat``/``lng`` 컬럼과
복합 인덱스가 있다.

사용자의 ``lat``/``lng``는 조회에만 쓰고 저장하지 않는다 (명세).

상태 신선도(BE-10): 충전기 상태는 수집 시각(``charger_cache.updated_at``)부터 낡는다.
``CHARGER_STATUS_STALE_MIN``(20)분을 넘으면 stale로 표시하고, ``CHARGER_STATUS_MAX_AGE_MIN``
(60)분을 넘으면 상태 미확인으로 보아 "비어 있음"(``available_only``, 경로 위 추천)으로 세지
않는다. 상태 판정은 아래 ``_ChargerFilter``와 ``_has_matching_charger`` 한 곳에서 한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session as DbSession

from ...domain.geo import bounding_box, haversine_m
from ...domain.pricing import KST
from ...infra.charger_sync import STATIONS_KIND, STATUS_KIND
from ...infra.db import get_session
from ...infra.models import ChargerCache, ChargerSyncState, FavoriteStation, User
from ...settings import get_settings
from ..auth_deps import optional_user
from ..schemas import MAX_CHARGER_KW, ChargerFreshnessOut, ChargerOut, StationOut

router = APIRouter(prefix="/api", tags=["chargers"])

# 인증 없이 닿는 경로라 상한을 둔다(I-4와 같은 이유). 20km면 나주·광주 전역을
# 덮고도 남는다. 상한이 없으면 반경 하나로 캐시 전체를 파이썬으로 끌어올 수 있다.
MAX_RADIUS_M = 20_000
DEFAULT_RADIUS_M = 2_000

# 공공 API 충전기 상태 코드(stat) 중 "충전대기" = 지금 꽂을 수 있음. 활용가이드의
# 다른 코드(통신이상·충전중·운영중지·점검중·상태미확인)는 비어 있다고 보지 않는다.
STATUS_AVAILABLE = "2"

# available_only로 찾았는데 오래된 상태만 있어 비었을 때 알리는 문장(GET /api/chargers는
# ``X-Status-Note`` 헤더, 경로 위 찾기는 coverage_note)
STATUS_UNKNOWN_NOTE = "충전기 상태 정보가 오래돼 비어 있는지 확인할 수 없어요."
STATUS_NOTE_HEADER = "X-Status-Note"


def now_kst() -> datetime:
    """서버 현재 시각. 테스트가 이 함수를 바꿔 시각을 고정한다."""
    return datetime.now(KST)


@dataclass(frozen=True)
class FreshnessLimits:
    stale_min: int
    max_age_min: int
    # 모든 충전소 상태를 여기까지 확인한 시각(``charger_sync_state``). 없으면 None
    confirmed_at: datetime | None = None
    # 마지막 전체 수집의 시작 시각. 이보다 이른 행은 그 수집에 없던 충전소다. 없으면 None
    stations_at: datetime | None = None

    @classmethod
    def current(cls, session: DbSession) -> FreshnessLimits:
        """요청마다 한 번 읽는다(설정은 캐시되지 않아 행마다 읽으면 느리다)."""
        settings = get_settings()
        marks = dict(
            session.execute(
                select(ChargerSyncState.kind, ChargerSyncState.confirmed_at).where(
                    ChargerSyncState.kind.in_((STATUS_KIND, STATIONS_KIND))
                )
            ).all()
        )
        return cls(
            settings.charger_status_stale_min,
            settings.charger_status_max_age_min,
            marks.get(STATUS_KIND),
            marks.get(STATIONS_KIND),
        )

    def confirms(self, updated_at: datetime) -> bool:
        """확인 시각을 이 행에 적용할 수 있는지: 마지막 전체 수집이 받은 행일 때만."""
        return (
            self.confirmed_at is not None
            and self.stations_at is not None
            and updated_at >= self.stations_at
        )


@dataclass(frozen=True)
class StatusAge:
    synced_at: datetime
    # 수집 뒤 지난 분(내림). 수집 시각이 지금보다 뒤면(시계 차이) 0
    age_min: int
    # age_min > stale_min
    stale: bool
    # age_min <= max_age_min: "충전대기"를 비어 있음으로 믿어도 되는지
    known: bool


def status_age(row: ChargerCache, now: datetime, limits: FreshnessLimits) -> StatusAge:
    """상태 시각은 ``max(행의 updated_at, 확인 시각)``이다(``ChargerSyncState`` 설명).

    마지막 전체 수집에 없던 행(``updated_at`` < 그 수집 시작)은 ``updated_at``만 쓴다.
    """
    synced = row.updated_at
    if limits.confirms(synced):
        synced = max(synced, limits.confirmed_at)
    synced = synced.astimezone(KST)
    age = max(0, math.floor((now - synced).total_seconds() / 60))
    return StatusAge(synced, age, age > limits.stale_min, age <= limits.max_age_min)


def charger_api_key() -> str:
    """설정의 공공 API 키.

    의존성으로 빼 둔 이유는 테스트가 ``dependency_overrides``로 "키 있음/없음"을
    직접 정할 수 있게 하기 위해서다 — 개발자 ``.env``에 키가 있느냐에 따라
    테스트 결과가 갈리면 안 된다.
    """
    return get_settings().charger_api_key


@router.get("/chargers", response_model=list[StationOut])
def list_chargers(
    response: Response,
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

    now = now_kst()
    limits = FreshnessLimits.current(session)
    query = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_m,
        "charger_type": charger_type,
        "available_only": available_only,
        "min_kw": min_kw,
    }
    result = search_nearby(session, **query, now=now, limits=limits)
    found = result.found

    if not found and cache_is_empty(session):
        # "주변에 충전소가 없다"와 "아직 수집하지 않았다"는 다른 말이다. 빈
        # 목록으로 답하면 화면이 나주에 충전소가 없다고 말하게 된다.
        raise HTTPException(
            status_code=503,
            detail=(
                "충전소 정보를 아직 수집하지 않았습니다. "
                "잠시 후 다시 시도해 주세요."
            ),
        )

    # 오래된 상태 때문에 비었으면 "주변에 빈 충전기가 없다"가 아니라 "확인할 수 없다"다.
    # 응답 본문은 목록이라 필드를 더할 수 없어 헤더로 알린다(UTF-8 퍼센트 인코딩).
    if result.empty_because_of_age:
        response.headers[STATUS_NOTE_HEADER] = quote(STATUS_UNKNOWN_NOTE)

    favorites = _favorite_ids(session, user, [row.station_id for _, row in found])

    return [
        _to_station_out(
            row, distance, favorites if user is not None else None, status_age(row, now, limits)
        )
        for distance, row in found
    ]


@router.get("/chargers/freshness", response_model=ChargerFreshnessOut)
def charger_freshness(session: DbSession = Depends(get_session)) -> ChargerFreshnessOut:
    """수집된 충전소(좌표 있는 행)의 상태 시각 범위와 stale 수. 집계 쿼리 한 번이다.

    운영 확인용 공개 API다. 위치나 개인정보는 없다. 캐시가 비면 시각은 null, 수는 0이다.
    """
    now = now_kst()
    limits = FreshnessLimits.current(session)
    # stale은 지난 분(내림)이 stale_min을 넘는 것, 즉 stale_min + 1분 이상 지난 행이다.
    stale_before = now - timedelta(minutes=limits.stale_min + 1)
    # 행별 상태 시각은 status_age와 같은 규칙이다. 마지막 전체 수집에 있던 행(updated_at >=
    # 그 시작)만 greatest(updated_at, 확인 시각), 나머지는 updated_at. 표시가 없으면(NULL)
    # 비교가 거짓이라 updated_at이다.
    def mark(kind: str):
        return (
            select(ChargerSyncState.confirmed_at)
            .where(ChargerSyncState.kind == kind)
            .scalar_subquery()
        )

    confirmed = mark(STATUS_KIND)
    synced = case(
        (
            and_(confirmed.is_not(None), ChargerCache.updated_at >= mark(STATIONS_KIND)),
            func.greatest(ChargerCache.updated_at, confirmed),
        ),
        else_=ChargerCache.updated_at,
    )
    latest, oldest, count, stale = session.execute(
        select(
            func.max(synced),
            func.min(synced),
            func.count(),
            func.count().filter(synced <= stale_before),
        ).where(ChargerCache.lat.is_not(None))
    ).one()
    return ChargerFreshnessOut(
        latest_synced_at=latest,
        oldest_synced_at=oldest,
        station_count=count,
        stale_count=stale,
    )


@dataclass(frozen=True)
class NearbyResult:
    # (거리 m, 캐시 행), 가까운 순
    found: list[tuple[float, ChargerCache]]
    # 상태가 오래돼서만 빠진 충전소가 있었다(상태가 새것이었다면 조건을 맞췄을 곳)
    hidden_by_age: bool

    @property
    def empty_because_of_age(self) -> bool:
        """비었고, 그 이유가 오래된 상태다: "없다"가 아니라 "확인할 수 없다"고 말할 때."""
        return not self.found and self.hidden_by_age


def find_nearby(
    session: DbSession,
    *,
    lat: float,
    lng: float,
    radius_m: int,
    charger_type: str | None = None,
    available_only: bool = False,
    min_kw: float | None = None,
    now: datetime,
    limits: FreshnessLimits,
) -> list[tuple[float, ChargerCache]]:
    """``search_nearby``의 목록만."""
    return search_nearby(
        session,
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        charger_type=charger_type,
        available_only=available_only,
        min_kw=min_kw,
        now=now,
        limits=limits,
    ).found


def search_nearby(
    session: DbSession,
    *,
    lat: float,
    lng: float,
    radius_m: int,
    charger_type: str | None = None,
    available_only: bool = False,
    min_kw: float | None = None,
    now: datetime,
    limits: FreshnessLimits,
) -> NearbyResult:
    """반경 안의 충전소를 가까운 순으로 (거리 m, 캐시 행). 필터 규칙은 위 쿼리 설명과 같다.

    ``available_only``는 상태 수집 뒤 ``limits.max_age_min``분 이하인 행만 센다.
    오래된 상태 때문에만 빠진 충전소가 있었는지도 같은 루프에서 센다(캐시를 다시 읽지 않는다).

    음성 대화(BE-3)의 ``find_chargers`` 도구도 HTTP를 거치지 않고 이 함수를 부른다.
    """
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
    hidden_by_age = False
    for row in candidates:
        # 2차 필터: 박스는 원보다 크다(모서리). 정확한 거리로 한 번 더 거른다.
        distance = haversine_m(lat, lng, row.lat, row.lng)
        if distance > radius_m:
            continue
        known = status_age(row, now, limits).known
        if wanted.is_set() and not _has_matching_charger(row, wanted, status_known=known):
            if not known and _has_matching_charger(row, wanted, status_known=True):
                hidden_by_age = True
            continue
        found.append((distance, row))
    found.sort(key=lambda item: item[0])
    return NearbyResult(found, hidden_by_age)


def charger_summary(row: ChargerCache) -> tuple[int, float | None]:
    """(지금 상태가 2(충전대기)인 충전기 수, 가장 높은 출력 kW). 출력 값이 이상하면 뺀다."""
    chargers = _chargers(row)
    available = sum(
        1 for charger in chargers if str(charger.get("status", "")).strip() == STATUS_AVAILABLE
    )
    outputs = [kw for kw in (_as_kw(charger.get("capacity_kw")) for charger in chargers) if kw]
    return available, max(outputs) if outputs else None


def matching_count(
    row: ChargerCache, *, available_only: bool, min_kw: float | None, status_known: bool
) -> int:
    """이 충전소에서 조건(지금 충전대기, 출력 ``min_kw`` 이상)을 한 대가 모두 맞는 충전기 수.

    ``find_nearby``와 같은 판정(``_ChargerFilter``)이다. 경로 위 충전소 찾기(BE-7)가 쓴다.
    ``status_known``이 거짓(상태가 오래됨)이면 ``available_only``에서 한 대도 세지 않는다.
    """
    wanted = _ChargerFilter(charger_type=None, available_only=available_only, min_kw=min_kw)
    if available_only and not status_known:
        return 0
    return sum(1 for charger in _chargers(row) if wanted.matches(charger))


def rows_in_boxes(
    session: DbSession, boxes: list[tuple[float, float, float, float]], *, limit: int | None = None
) -> list[ChargerCache]:
    """사각형들 ``(min_lat, min_lng, max_lat, max_lng)`` 중 하나라도 안에 있는 캐시 행.

    인덱스를 타는 범위 비교의 OR이다. 좌표가 없는 행은 빠진다. ``limit``이 있으면 행이
    들어 있는 첫 사각형의 순서대로 그 수만큼만 읽는다(사각형을 경로 순서로 주면 앞쪽
    구간부터).
    """
    if not boxes:
        return []
    conditions = [
        and_(
            ChargerCache.lat.between(min_lat, max_lat),
            ChargerCache.lng.between(min_lng, max_lng),
        )
        for min_lat, min_lng, max_lat, max_lng in boxes
    ]
    query = select(ChargerCache).where(or_(*conditions))
    if limit is not None:
        first_box = case(*[(c, i) for i, c in enumerate(conditions)], else_=len(conditions))
        query = query.order_by(first_box, ChargerCache.station_id).limit(limit)
    return list(session.scalars(query).all())


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


def _has_matching_charger(
    row: ChargerCache, wanted: _ChargerFilter, *, status_known: bool
) -> bool:
    """주어진 조건을 **같은 충전기 한 대가** 모두 맞으면 그 충전소를 남긴다.

    걸러내는 단위는 충전기가 아니라 충전소다 — 조건에 맞는 충전기가 있는
    충전소를 찾는 화면이므로, 그 충전소의 나머지 충전기도 함께 보여준다.
    조건을 충전기마다 따로 보면 "7kW 충전대기 + 100kW 충전중" 충전소가
    "100kW 이상 빈 충전기" 조건에 걸려, 차 안에서 헛걸음하게 된다.

    상태가 오래된 행(``status_known`` 거짓)은 ``available_only``를 맞출 수 없다. "충전대기"가
    한 시간 전 값이면 지금 비어 있다고 말할 근거가 아니다.
    """
    if wanted.available_only and not status_known:
        return False
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


def cache_is_empty(session: DbSession) -> bool:
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
    row: ChargerCache, distance_m: float, favorites: set[str] | None, age: StatusAge
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
        synced_at=age.synced_at,
        status_age_min=age.age_min,
        stale=age.stale,
    )

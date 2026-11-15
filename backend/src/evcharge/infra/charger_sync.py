"""공공 API → ``charger_cache`` 수집기 (F-07).

캐시가 필수인 이유: 개발계정 트래픽이 하루 1,000건이라 사용자 요청마다 공공
API를 부르면 즉시 넘친다. 여기서 캐시를 채우고 ``GET /api/chargers``는 캐시만
읽는다. 호출 예산은 전체 수집 4건/회(zcode=12 기준 32,835건 ÷ 9,999),
상태 수집 1~2건/회다.

**충전기 1대당 1행**으로 오는 응답을 ``statId``로 묶어 충전소 1건 = 캐시 1행으로
저장한다. ``data`` JSONB는 ``api.schemas.StationOut``이 그대로 읽을 수 있는
모양이며, 그 덕에 F-14 즐겨찾기 목록(``routes/me_favorites.py``)도 같은 행에서
이름·주소를 꺼낸다.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from ..domain.pricing import KST
from .models import ChargerCache, ChargerFullSyncRun, ChargerSyncState

# charger_sync_state의 두 행: 상태를 여기까지 확인한 시각, 마지막 전체 수집이 시작한 시각
STATUS_KIND = "status"
STATIONS_KIND = "stations"

logger = logging.getLogger(__name__)

# 한 번에 INSERT하는 행 수. 3만 건을 한 문장에 넣으면 파라미터 한도에 걸린다.
UPSERT_CHUNK = 500

# statUpdDt 형식: "20260921212933" (KST 벽시계, 타임존 표기 없음)
STAT_UPD_FORMAT = "%Y%m%d%H%M%S"


class ChargerApi(Protocol):
    """수집기가 클라이언트에 기대하는 것 전부.

    구체 클래스가 아니라 프로토콜을 받는 이유는 테스트에서 고정 응답을 돌려주는
    가짜를 끼우기 위해서다 — 테스트가 하루 1,000건 할당량을 갉아먹으면 안 된다.
    """

    def fetch_station_rows(self, zcode: str) -> list[dict]: ...

    def fetch_status_rows(self, zcode: str, period: int) -> list[dict]: ...


@dataclass(frozen=True)
class StationRecord:
    """캐시 한 행. ``lat``/``lng``는 ``data`` 안에도 있지만 컬럼으로도 쓴다."""

    station_id: str
    lat: float
    lng: float
    data: dict


@dataclass(frozen=True)
class StationSyncResult:
    api_rows: int
    stations: int
    chargers: int
    dropped_rows: int


@dataclass(frozen=True)
class StatusSyncResult:
    api_rows: int
    stations_updated: int
    chargers_updated: int
    unknown_rows: int
    # 확인 시각을 이번 수집 시작으로 앞당겼는지. 거짓이면 수집 창이 끊겼거나 기준이 없다.
    confirmed: bool = True
    # 끊김을 보고 그 자리에서 돌린 전체 수집의 결과(돌리지 않았으면 None)
    recovered: StationSyncResult | None = None

# 전체 수집 기록을 남기는 기간. 하루 한도만 세면 되므로 이틀이면 충분하다.
RUN_RETENTION = timedelta(days=2)


def build_station_records(rows: Iterable[dict]) -> list[StationRecord]:
    """``getChargerInfo`` 행들을 충전소 단위로 묶는다.

    같은 ``statId``의 첫 행이 이름·주소·좌표를 정한다(모든 행이 같은 값을 싣는다).
    좌표를 읽을 수 없는 행은 버린다 — 반경 조회에 쓸 수 없고 ``StationOut``의
    필수 필드도 채우지 못한다.
    """
    stations: dict[str, dict] = {}
    coordinates: dict[str, tuple[float, float]] = {}

    for row in rows:
        station_id = str(row.get("statId") or "").strip()
        if not station_id:
            continue

        lat = _as_float(row.get("lat"))
        lng = _as_float(row.get("lng"))
        if lat is None or lng is None:
            continue

        document = stations.get(station_id)
        if document is None:
            document = {
                "name": str(row.get("statNm") or "").strip(),
                "address": _address(row),
                "lat": lat,
                "lng": lng,
                # busiNm(사업자명)이 비면 bnm(운영기관 약칭)으로 대체한다.
                "operator": str(row.get("busiNm") or row.get("bnm") or "").strip(),
                "available_hours": str(row.get("useTime") or "").strip(),
                "chargers": [],
            }
            stations[station_id] = document
            coordinates[station_id] = (lat, lng)

        document["chargers"].append(_charger(row))

    records = []
    for station_id, document in stations.items():
        # 응답 순서가 뒤섞여도 화면의 충전기 순서가 흔들리지 않게 고정한다.
        document["chargers"].sort(key=lambda charger: charger["charger_id"])
        lat, lng = coordinates[station_id]
        records.append(StationRecord(station_id=station_id, lat=lat, lng=lng, data=document))
    return records


def sync_stations(
    session: DbSession, api: ChargerApi, zcodes: Sequence[str]
) -> StationSyncResult:
    """전체 수집. 충전소 상세를 받아 캐시를 통째로 upsert한다.

    성공하면 모든 충전소 상태를 수집 시작 시각까지 확인한 것이다(``ChargerSyncState``).
    """
    started = _clock(session)
    rows: list[dict] = []
    for zcode in zcodes:
        fetched = api.fetch_station_rows(zcode)
        logger.info("zcode=%s 충전기 %d행", zcode, len(fetched))
        rows.extend(fetched)

    records = build_station_records(rows)
    _upsert(session, records)
    # 이번 수집이 쓴 행은 updated_at == started다(같은 트랜잭션의 now()). 그보다 이른 행은
    # 이번 응답에 없던 충전소(폐쇄, ID 변경, 지역 제외)라 확인 시각을 적용하지 않는다.
    _mark(session, STATIONS_KIND, started)
    _confirm(session, started, window=None)
    session.commit()

    chargers = sum(len(record.data["chargers"]) for record in records)
    return StationSyncResult(
        api_rows=len(rows),
        stations=len(records),
        chargers=chargers,
        dropped_rows=len(rows) - chargers,
    )


def sync_states(
    session: DbSession,
    api: ChargerApi,
    zcodes: Sequence[str],
    period: int = 10,
    *,
    recover_daily_max: int | None = None,
) -> StatusSyncResult:
    """상태만 갱신. 전체 재수집보다 훨씬 싸다(zcode=12, period=10에 964건).

    이름이 ``sync_status``가 아닌 이유: 이 함수가 갱신하는 것은 충전소 문서의
    ``status`` 필드이지 이 함수의 상태가 아니다. 캐시에 없는 충전소·충전기는
    만들지 않는다 — 상태 응답에는 종류·용량·주소가 없어서 ``StationOut``을
    채울 수 없다. 그건 전체 수집의 몫이다.

    수집 창이 끊겨 확인 시각을 앞당기지 못하면(또는 기준이 아직 없으면), ``recover_daily_max``가
    주어졌을 때 오늘(KST) 전체 수집이 그 횟수보다 적은 경우에만 그 자리에서 전체 수집을 돌린다.
    한 번 끊기면 다음 상태 수집도 계속 끊긴 것으로 판정되므로, 되살리지 않으면 다음 정기 전체
    수집까지 바뀌지 않은 빈 충전기가 "상태 미확인"으로 숨는다.
    """
    started = _clock(session)
    rows: list[dict] = []
    lags: list[float] = []
    for zcode in zcodes:
        fetched = api.fetch_status_rows(zcode, period)
        lags.extend(status_lag_minutes(fetched, received_at=_now()))
        logger.info("zcode=%s 상태 %d행", zcode, len(fetched))
        rows.extend(fetched)
    _log_lag(lags)

    by_station: dict[str, list[dict]] = {}
    for row in rows:
        station_id = str(row.get("statId") or "").strip()
        if station_id:
            by_station.setdefault(station_id, []).append(row)

    unknown = len(rows) - sum(len(v) for v in by_station.values())
    updated_stations = 0
    updated_chargers = 0

    for chunk in _chunks(list(by_station), UPSERT_CHUNK):
        cached = session.scalars(
            select(ChargerCache).where(ChargerCache.station_id.in_(chunk))
        ).all()
        found = {cache.station_id: cache for cache in cached}
        unknown += sum(
            len(by_station[station_id]) for station_id in chunk if station_id not in found
        )

        for station_id, cache in found.items():
            # JSONB는 제자리 수정(dict 내부 변경)을 SQLAlchemy가 못 알아채므로
            # 새 dict를 만들어 통째로 대입한다.
            document = dict(cache.data)
            chargers = [dict(charger) for charger in document.get("chargers", [])]
            index = {charger["charger_id"]: charger for charger in chargers}

            touched = 0
            for row in by_station[station_id]:
                charger = index.get(str(row.get("chgerId") or "").strip())
                if charger is None:
                    unknown += 1
                    continue
                charger["status"] = str(row.get("stat") or "").strip()
                charger["status_updated_at"] = _status_time(row.get("statUpdDt"))
                touched += 1

            if touched:
                document["chargers"] = chargers
                cache.data = document
                cache.updated_at = func.now()
                updated_stations += 1
                updated_chargers += touched

    confirmed = _confirm(session, started, window=timedelta(minutes=period))
    session.commit()
    recovered = None
    if not confirmed and recover_daily_max is not None:
        recovered = _recover(session, api, zcodes, recover_daily_max)
    return StatusSyncResult(
        confirmed=confirmed,
        recovered=recovered,
        api_rows=len(rows),
        stations_updated=updated_stations,
        chargers_updated=updated_chargers,
        unknown_rows=unknown,
    )


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------


def _clock(session: DbSession) -> datetime:
    """이번 트랜잭션의 시작 시각(``now()``). 공공 API를 부르기 전이고, 이 트랜잭션이
    캐시 행에 찍는 ``updated_at``(``func.now()``)과 같은 값이다.
    """
    return session.scalar(select(func.now()))


def _mark(session: DbSession, kind: str, at: datetime) -> None:
    state = session.get(ChargerSyncState, kind, with_for_update=True)
    if state is None:
        session.add(ChargerSyncState(kind=kind, confirmed_at=at))
    else:
        state.confirmed_at = at


def _now() -> datetime:
    """받은 시각. 테스트가 바꿔 고정한다."""
    return datetime.now(KST)


def status_lag_minutes(rows: Iterable[dict], *, received_at: datetime) -> list[float]:
    """행마다 (받은 시각 - 운영기관이 적은 상태 변경 시각 ``statUpdDt``), 분.

    운영기관이 상태를 늦게 올리면 수집 창(최근 N분)에 잡히지 않는 변경이 생긴다. 그 지연을
    운영 로그로 재 보려는 값이다. 읽을 수 없는 시각은 뺀다. 음수(운영기관 시계가 빠름)도
    그대로 둔다.
    """
    lags = []
    for row in rows:
        stamp = _status_time(row.get("statUpdDt"))
        if stamp is not None:
            lags.append((received_at - datetime.fromisoformat(stamp)).total_seconds() / 60)
    return lags


def _log_lag(lags: list[float]) -> None:
    """한 회차의 반영 지연을 INFO 한 줄로. 값만 남긴다(충전소 ID 없음)."""
    if not lags:
        return
    logger.info(
        "상태 반영 지연: %d행, 중앙값 %.1f분, 최대 %.1f분",
        len(lags),
        statistics.median(lags),
        max(lags),
    )


def record_full_sync_run(session: DbSession, *, recovery: bool) -> None:
    """전체 수집을 시작한다는 기록을 남기고 바로 커밋한다(공공 API를 부르기 전)."""
    session.execute(
        delete(ChargerFullSyncRun).where(
            ChargerFullSyncRun.started_at < func.now() - RUN_RETENTION
        )
    )
    session.add(ChargerFullSyncRun(recovery=recovery))
    session.commit()


def full_syncs_today(session: DbSession) -> int:
    """오늘(KST 0시부터) 시작한 전체 수집 수. 실패한 수집도 센다."""
    now = _clock(session).astimezone(KST)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return session.scalar(
        select(func.count()).where(ChargerFullSyncRun.started_at >= midnight)
    )


def _recover(
    session: DbSession, api: ChargerApi, zcodes: Sequence[str], daily_max: int
) -> StationSyncResult | None:
    done = full_syncs_today(session)
    if done >= daily_max:
        logger.warning(
            "상태 수집이 끊겼지만 오늘 전체 수집이 이미 %d회라(한도 %d) 되살리지 않습니다. "
            "다음 정기 전체 수집 전까지 바뀌지 않은 충전소는 상태 미확인으로 보일 수 있습니다.",
            done,
            daily_max,
        )
        return None
    logger.warning("상태 수집이 끊겨 전체 수집으로 확인 시각을 되살립니다 (오늘 %d회째)", done + 1)
    record_full_sync_run(session, recovery=True)
    return sync_stations(session, api, zcodes)


def _confirm(session: DbSession, started: datetime, *, window: timedelta | None) -> bool:
    """확인 시각을 ``started``로 앞당긴다. ``window``는 상태 수집이 받은 변경 기간이다.

    상태 수집은 ``started - window``가 지난 확인 시각 이전일 때만(수집 창이 이어질 때만)
    앞당긴다. 수집이 끊겼던 동안의 변경은 놓쳤으므로, 바뀌지 않은 충전소를 확인했다고
    말할 수 없다. 확인 시각이 아직 없으면 상태 수집은 기준을 만들 수 없다(전체 수집이 만든다).
    전체 수집(``window=None``)은 모든 충전소를 새로 받으므로 언제나 앞당긴다.
    앞당겼으면 True.
    """
    state = session.get(ChargerSyncState, STATUS_KIND, with_for_update=True)
    if state is None:
        if window is None:
            session.add(ChargerSyncState(kind=STATUS_KIND, confirmed_at=started))
            return True
        logger.warning("상태 확인 시각이 아직 없습니다 (전체 수집 전)")
        return False
    if window is not None and started - window > state.confirmed_at:
        logger.warning(
            "상태 수집이 끊겼던 구간이 있어 확인 시각을 앞당기지 않습니다 (마지막 확인 %s)",
            state.confirmed_at.isoformat(),
        )
        return False
    state.confirmed_at = max(state.confirmed_at, started)
    return True


def _upsert(session: DbSession, records: Sequence[StationRecord]) -> None:
    """``station_id`` 충돌 시 갱신. 캐시는 전 사용자 공유라 지우고 다시 넣지
    않는다 — 그 사이에 들어온 조회가 빈 결과를 보게 된다."""
    for chunk in _chunks(records, UPSERT_CHUNK):
        values = [
            {
                "station_id": record.station_id,
                "data": record.data,
                "lat": record.lat,
                "lng": record.lng,
            }
            for record in chunk
        ]
        statement = pg_insert(ChargerCache).values(values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[ChargerCache.station_id],
                set_={
                    "data": statement.excluded.data,
                    "lat": statement.excluded.lat,
                    "lng": statement.excluded.lng,
                    "updated_at": func.now(),
                },
            )
        )


def _chunks(items: Sequence, size: int) -> Iterable[Sequence]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _charger(row: dict) -> dict:
    """``ChargerOut`` 한 건.

    ``type``(chgerType)과 ``status``(stat)는 **원문 그대로** 싣는다. 공식
    활용가이드를 확보하지 못해 코드표를 확인할 수 없고(실제 데이터의 11.9%가
    표에 없는 ``9``다), 추정 매핑은 '사용 가능'이라 적힌 자리에 사용자를
    헛걸음시킨다. 프론트는 모르는 코드를 원문 표시하고 사용 가능으로 세지 않는다.
    """
    return {
        "charger_id": str(row.get("chgerId") or "").strip(),
        "type": str(row.get("chgerType") or "").strip(),
        # 출력이 비어 있어도 충전기를 버리지는 않는다. ChargerOut.capacity_kw가
        # 필수라 숫자는 넣어야 하고, 0은 화면에서 "0kW"로 그대로 보인다.
        "capacity_kw": _as_float(row.get("output")) or 0.0,
        "status": str(row.get("stat") or "").strip(),
        "status_updated_at": _status_time(row.get("statUpdDt")),
    }


def _address(row: dict) -> str:
    address = str(row.get("addr") or "").strip()
    detail = str(row.get("addrDetail") or "").strip()
    return f"{address} {detail}".strip() if detail else address


def _status_time(value: object) -> str | None:
    """``"20260921212933"`` → ``"2026-09-21T21:29:33+09:00"``.

    타임존 표기가 없는 KST 벽시계다. 읽을 수 없으면 ``None`` — 지금 시각으로
    채우면 "방금 확인된 상태"라고 거짓말하게 된다.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, STAT_UPD_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=KST).isoformat()


def _as_float(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None

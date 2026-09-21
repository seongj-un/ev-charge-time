"""F-09 태양광 발전 예측 — 지역 해석 · 예보 조회 · 캐시 · 응답 조립.

물리 계산은 ``domain/solar.py``, 격자 변환은 ``domain/kma_grid.py``, API 호출은
``infra/kma_api.py``에 있다. 이 모듈은 그것들을 엮고 HTTP 경계의 판단(어떤 지역
이름을 받을지, 자료가 없을 때 몇 번으로 답할지)을 맡는다.

──────────────────────────────────────────────────────────────────────────
명세와 어긋나는 지점: ``predicted_mwh``
──────────────────────────────────────────────────────────────────────────

API 명세 5-1의 응답 필드는 ``hours[].predicted_mwh`` — **시도 전체의 발전량**이다.
그런데 물리 근사가 내놓는 것은 **단위면적당 일사량(W/m²)**이고, 이걸 MWh로
바꾸려면 그 지역의 **태양광 설비용량**이 필요하다. 그건 전력거래소 자료이고
이 프로젝트에는 없다.

그래서 이렇게 한다:

* ``ghi_wm2``·``clear_sky_ghi_wm2``·``output_index``는 **항상** 채운다. 모델이
  실제로 계산해 내는 값이라 언제나 진짜다.
* ``predicted_mwh``는 **설비용량이 설정돼 있을 때만** 채우고, 없으면 ``null``이다.
  없는 자료로 MWh를 지어내는 것이 제일 나쁜 선택이므로, 비어 있다는 사실을
  그대로 드러낸다. 필드를 지우지 않고 남겨 둔 이유는 명세의 계약을 유지하고
  자료가 생기면 API 변경 없이 채워지게 하기 위해서다.
* 설비용량은 **출처(``solar_capacity_source``)를 함께 적었을 때만** 쓴다. 출처
  없는 숫자는 지어낸 숫자와 구별되지 않는다 — 이 저장소가 요금 잠정치에
  ``source``·``status``를 달아 온 것과 같은 규칙이다.

차트에 겹쳐 그리는 용도에는 ``output_index``(STC 1000 W/m² 대비 0~1)가 바로
쓰인다. 하루 안의 최대값이 아니라 **고정 기준(STC)**으로 정규화하므로 흐린 날과
맑은 날이 서로 다른 높이로 그려진다 — 날마다 최대를 1.0으로 맞추면 "오늘은
흐리다"는 정보가 사라진다.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from fastapi import HTTPException

from ..domain.kma_grid import grid_to_latlng, latlng_to_grid
from ..domain.pricing import KST
from ..domain.solar import (
    MODEL_VERSION,
    UnknownSkyCodeError,
    clear_sky_ghi_wm2,
    cloud_transmittance,
    output_index,
)
from ..infra.kma_api import KmaApiError, KmaNoDataError, latest_settled_base_time, previous_issuance
from .schemas import SolarForecast, SolarHour

logger = logging.getLogger(__name__)

# 발표가 NO_DATA일 때 몇 번이나 이전 발표로 물러설지. 3이면 최대 9시간 전까지
# 훑는다 — 그보다 오래된 예보는 '오늘/내일' 예측으로서 의미가 떨어진다.
MAX_FALLBACKS = 3

# 인버터 손실·온도 손실·경사각 차이를 묶은 시스템 효율(performance ratio).
# 설비용량이 설정됐을 때 MWh 환산에만 쓴다. 0.8은 NREL PVWatts의 기본 손실
# 모형이 내는 범위(대략 0.75~0.85)의 가운데 값이다. 기본 설정에서는 설비용량이
# 비어 있어 이 상수가 쓰이지 않는다.
PERFORMANCE_RATIO = 0.8


class KmaApi(Protocol):
    """서비스가 클라이언트에 기대하는 것 전부.

    구체 클래스가 아니라 프로토콜을 받는 이유는 테스트에서 고정 응답을
    돌려주는 가짜를 끼우기 위해서다 — 테스트가 실제 API를 부르면 안 된다.
    """

    def fetch_village_forecast(
        self, nx: int, ny: int, base_date: str, base_time: str
    ) -> list[dict]: ...


@dataclass(frozen=True)
class Region:
    """예보를 받을 대표 지점.

    **5km 격자 한 칸이 시도 전체를 대신한다.** 전남처럼 넓은 지역은 동쪽 끝과
    서쪽 끝의 하늘이 다를 수 있다. 응답의 ``assumptions``에 이 사실을 싣는다.
    """

    name: str
    lat: float
    lng: float


# 시도 대표 지점(시청·도청 소재지) + 대회 지역.
#
# 전남을 무안(도청)이 아니라 나주로 잡은 이유: 이 서비스의 사용자는 빛가람
# 혁신도시에 있고, 어차피 격자 한 칸이 도 전체를 대표하지 못한다면 사용자가
# 있는 칸을 고르는 편이 쓸모 있다. 같은 격자를 "나주"·"빛가람"으로도 부를 수 있다.
_REGIONS: tuple[tuple[Region, tuple[str, ...]], ...] = (
    (Region("서울", 37.5665, 126.9780), ("서울", "서울특별시", "서울시")),
    (Region("부산", 35.1798, 129.0750), ("부산", "부산광역시", "부산시")),
    (Region("대구", 35.8714, 128.6014), ("대구", "대구광역시", "대구시")),
    (Region("인천", 37.4563, 126.7052), ("인천", "인천광역시", "인천시")),
    (Region("광주", 35.1600, 126.8514), ("광주", "광주광역시", "광주시")),
    (Region("대전", 36.3504, 127.3845), ("대전", "대전광역시", "대전시")),
    (Region("울산", 35.5384, 129.3114), ("울산", "울산광역시", "울산시")),
    (Region("세종", 36.4800, 127.2890), ("세종", "세종특별자치시", "세종시")),
    (Region("경기", 37.2750, 127.0095), ("경기", "경기도")),
    (Region("강원", 37.8813, 127.7300), ("강원", "강원도", "강원특별자치도")),
    (Region("충북", 36.6357, 127.4917), ("충북", "충청북도")),
    (Region("충남", 36.6588, 126.6728), ("충남", "충청남도")),
    (Region("전북", 35.8203, 127.1088), ("전북", "전라북도", "전북특별자치도")),
    (
        Region("전남", 35.0197, 126.7893),
        ("전남", "전라남도", "나주", "나주시", "빛가람", "빛가람동", "빛가람혁신도시"),
    ),
    (Region("경북", 36.5760, 128.5056), ("경북", "경상북도")),
    (Region("경남", 35.2384, 128.6923), ("경남", "경상남도")),
    (Region("제주", 33.4996, 126.5312), ("제주", "제주도", "제주특별자치도", "제주시")),
)

REGION_BY_ALIAS: dict[str, Region] = {
    alias: region for region, aliases in _REGIONS for alias in aliases
}
REGION_NAMES: tuple[str, ...] = tuple(region.name for region, _ in _REGIONS)


def resolve_region(name: str) -> Region:
    """지역 이름 → 대표 지점. 모르는 이름은 아는 목록과 함께 422로 돌려준다."""
    region = REGION_BY_ALIAS.get(name.strip())
    if region is None:
        raise HTTPException(
            status_code=422,
            detail=f"알 수 없는 지역입니다: {name}. 가능한 값: {', '.join(REGION_NAMES)}",
        )
    return region


# (fcstDate, fcstTime) → {category: value}
SlotMap = dict[tuple[str, str], dict[str, str]]


def build_slot_map(rows: list[dict]) -> SlotMap:
    """예보 행들을 (예보시각 → 항목) 표로 접는다.

    한 행이 (예보시각, 항목) 하나라서, 시간대별로 SKY·PTY를 함께 보려면
    이렇게 모아야 한다.
    """
    slots: SlotMap = {}
    for row in rows:
        fcst_date = str(row.get("fcstDate") or "")
        fcst_time = str(row.get("fcstTime") or "")
        category = str(row.get("category") or "")
        if not (fcst_date and fcst_time and category):
            continue
        slots.setdefault((fcst_date, fcst_time), {})[category] = str(row.get("fcstValue") or "")
    return slots


def covers_a_full_day(slots: SlotMap) -> bool:
    """어느 하루든 24시간이 온전히 들어 있는가.

    실측에서 **가장 최근 발표는 잠시 '반쯤 쓰인' 상태로 오고, 그래도
    ``resultCode``는 00이었다** (같은 요청이 408행/980행을 번갈아 돌려줬다).
    "오류 없이 일부만 온다"가 가장 위험한 실패라, 캐시에 넣기 전에 한 번 거른다.

    안정된 발표는 항상 '내일'과 '모레'를 24시간씩 싣고 있으므로 이 검사를
    통과한다. 잘린 응답은 통과하지 못한다.
    """
    per_day: dict[str, set[str]] = {}
    for (fcst_date, fcst_time), values in slots.items():
        if "SKY" in values:
            per_day.setdefault(fcst_date, set()).add(fcst_time)
    return any(len(times) >= 24 for times in per_day.values())


@dataclass
class _Issuance:
    base_date: str
    base_time: str
    slots: SlotMap


class ForecastCache:
    """발표 단위 캐시.

    키에 발표(base_date·base_time)가 들어 있어 값이 한 번 채워지면 변하지
    않는다 — 그래서 TTL이 필요 없고, 크기 상한만 둔다. 새 발표가 나오면
    자연히 새 키가 되고 오래된 항목이 밀려난다.
    """

    def __init__(self, max_entries: int = 64) -> None:
        self._entries: OrderedDict[tuple, SlotMap] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: tuple) -> SlotMap | None:
        slots = self._entries.get(key)
        if slots is not None:
            self._entries.move_to_end(key)
        return slots

    def put(self, key: tuple, slots: SlotMap) -> None:
        self._entries[key] = slots
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


@dataclass
class SolarForecastService:
    """지역·날짜를 받아 시간별 예측을 조립한다."""

    client: KmaApi
    # 지역명 → 설비용량(MW). 출처가 비어 있으면 통째로 무시한다.
    capacities: dict[str, float] = field(default_factory=dict)
    capacity_source: str = ""
    clock: Callable[[], datetime] = lambda: datetime.now(KST)
    cache: ForecastCache = field(default_factory=ForecastCache)

    def forecast(self, region_name: str, day: date) -> SolarForecast:
        region = resolve_region(region_name)
        nx, ny = latlng_to_grid(region.lat, region.lng)
        issuance = self._load_issuance(nx, ny)

        # 격자 중심 좌표로 계산한다 — 예보가 대표하는 지점이 거기이기 때문이다.
        grid_lat, grid_lng = grid_to_latlng(nx, ny)
        capacity = self._capacity_for(region.name)

        assumptions = [
            f"{region.name} 전체를 기상청 5km 격자 한 칸(nx={nx}, ny={ny})의 예보로 대신합니다.",
            f"기상청 단기예보 {issuance.base_date} {issuance.base_time} 발표를 사용했습니다.",
        ]

        hours: list[SolarHour] = []
        unknown_sky: list[int] = []
        for hour in range(24):
            values = issuance.slots.get((day.strftime("%Y%m%d"), f"{hour:02d}00"))
            if values is None or "SKY" not in values:
                continue

            sky = values.get("SKY", "")
            pty = values.get("PTY", "")
            when = datetime(day.year, day.month, day.day, hour, 30, tzinfo=KST)
            # 정각이 아니라 30분을 쓰는 이유: 그 값은 "그 시간대"의 예보이므로
            # 한가운데를 대표로 삼는 편이 시간 평균에 가깝다.
            clear = clear_sky_ghi_wm2(grid_lat, grid_lng, when)

            if clear <= 0.0:
                ghi = 0.0
            else:
                try:
                    ghi = clear * cloud_transmittance(sky, pty)
                except UnknownSkyCodeError:
                    # 모르는 코드에 그럴듯한 감쇠를 매기지 않는다. 그 시간대만 뺀다.
                    logger.warning("모르는 SKY 코드 %r — %s %02d시를 건너뛴다", sky, day, hour)
                    unknown_sky.append(hour)
                    continue

            index = output_index(ghi)
            hours.append(
                SolarHour(
                    hour=hour,
                    ghi_wm2=round(ghi, 1),
                    clear_sky_ghi_wm2=round(clear, 1),
                    output_index=round(index, 4),
                    predicted_mwh=(
                        round(index * capacity * PERFORMANCE_RATIO, 3)
                        if capacity is not None
                        else None
                    ),
                    sky=sky,
                    pty=pty,
                )
            )

        if not hours:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{day}의 예보가 없습니다. 기상청 단기예보의 시간별 자료는 "
                    "발표일로부터 약 2일까지만 제공됩니다."
                ),
            )

        if len(hours) + len(unknown_sky) < 24:
            assumptions.append(
                f"이 발표에는 {day}의 일부 시간대만 들어 있어 "
                f"{len(hours)}개 시간만 예측했습니다."
            )
        if unknown_sky:
            assumptions.append(
                "모르는 하늘상태(SKY) 코드가 있어 "
                f"{len(unknown_sky)}개 시간을 제외했습니다: "
                + ", ".join(f"{h:02d}시" for h in unknown_sky)
            )
        if capacity is None:
            assumptions.append(
                "지역 태양광 설비용량 자료가 없어 predicted_mwh는 비워 둡니다. "
                "일사량(ghi_wm2)과 STC 대비 지수(output_index)는 그대로 유효합니다."
            )
        else:
            assumptions.append(
                f"설비용량 {capacity}MW, 시스템 효율 {PERFORMANCE_RATIO}로 환산했습니다 "
                f"(출처: {self.capacity_source})."
            )

        return SolarForecast(
            region=region.name,
            day=day,
            model_version=MODEL_VERSION,
            hours=hours,
            grid_nx=nx,
            grid_ny=ny,
            base_date=issuance.base_date,
            base_time=issuance.base_time,
            installed_capacity_mw=capacity,
            # capacity가 채워졌다는 것은 출처도 적혀 있다는 뜻이다(_capacity_for 참고).
            capacity_source=self.capacity_source if capacity is not None else None,
            assumptions=assumptions,
        )

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _capacity_for(self, region_name: str) -> float | None:
        """설비용량. **출처가 없으면 값이 있어도 쓰지 않는다.**"""
        if not self.capacity_source.strip():
            return None
        return self.capacities.get(region_name)

    def _load_issuance(self, nx: int, ny: int) -> _Issuance:
        """가장 최근 안정 발표부터 시작해, 자료가 없으면 이전 발표로 물러선다."""
        base_date, base_time = latest_settled_base_time(self.clock())
        errors: list[str] = []

        for _ in range(MAX_FALLBACKS + 1):
            key = (nx, ny, base_date, base_time)
            cached = self.cache.get(key)
            if cached is not None:
                return _Issuance(base_date, base_time, cached)

            try:
                rows = self.client.fetch_village_forecast(
                    nx=nx, ny=ny, base_date=base_date, base_time=base_time
                )
            except KmaNoDataError:
                errors.append(f"{base_date} {base_time}: 자료 없음")
            except KmaApiError as exc:
                # 호출 자체가 실패했다. 이전 발표를 불러도 같은 이유로 실패할
                # 가능성이 높으므로 여기서 멈춘다 — 할당량을 헛되이 쓰지 않는다.
                logger.warning("단기예보 호출 실패: %s", exc)
                raise HTTPException(
                    status_code=503,
                    detail="기상청 예보를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.",
                ) from exc
            else:
                slots = build_slot_map(rows)
                if covers_a_full_day(slots):
                    self.cache.put(key, slots)
                    return _Issuance(base_date, base_time, slots)
                # 반쯤 쓰인 발표일 수 있다. 캐시에 넣지 않고 이전 발표로 간다.
                logger.warning(
                    "단기예보 %s %s 응답이 하루를 못 채운다(%d 시간대) — 이전 발표로 물러선다",
                    base_date,
                    base_time,
                    len(slots),
                )
                errors.append(f"{base_date} {base_time}: 자료가 불완전함")

            base_date, base_time = previous_issuance(base_date, base_time)

        logger.warning("쓸 수 있는 단기예보 발표를 찾지 못했다: %s", "; ".join(errors))
        raise HTTPException(
            status_code=503,
            detail="기상청 예보를 아직 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )


def parse_capacities(raw: str) -> dict[str, float]:
    """``"전남:1234.5,광주:210"`` 형식을 dict로. 잘못된 항목은 건너뛰고 경고한다.

    설정 오타 하나로 서버가 안 뜨는 것보다, 그 지역만 ``predicted_mwh``가
    null로 남고 로그에 남는 편이 낫다 — 나머지 응답은 그대로 유효하다.
    """
    capacities: dict[str, float] = {}
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        name, separator, value = item.partition(":")
        if not separator:
            logger.warning("SOLAR_CAPACITY_MW 항목에 ':'가 없다: %r", item)
            continue
        try:
            capacities[name.strip()] = float(value)
        except ValueError:
            logger.warning("SOLAR_CAPACITY_MW 값이 숫자가 아니다: %r", item)
    return capacities


__all__ = [
    "MAX_FALLBACKS",
    "PERFORMANCE_RATIO",
    "REGION_NAMES",
    "ForecastCache",
    "KmaApi",
    "Region",
    "SolarForecastService",
    "build_slot_map",
    "covers_a_full_day",
    "parse_capacities",
    "resolve_region",
]

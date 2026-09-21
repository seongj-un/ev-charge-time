"""충전소 캐시 수집 실행 진입점 (F-07).

    uv run python -m evcharge.sync              # 전체 수집 (충전소 상세, 4호출)
    uv run python -m evcharge.sync --states     # 상태만 갱신 (1~2호출, 훨씬 싸다)
    uv run python -m evcharge.sync --states --period 5

cron이나 워커는 여기 없다 — 실행 방법만 제공한다. 5분마다 상태를 받아도
하루 300건 안쪽이라 개발계정 한도(1,000건) 안에 든다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from .infra.charger_api import ChargerApiClient, ChargerApiError
from .infra.charger_sync import (
    StationSyncResult,
    StatusSyncResult,
    sync_states,
    sync_stations,
)
from .infra.db import session_scope
from .settings import get_settings

logger = logging.getLogger("evcharge.sync")

__all__ = [
    "ChargerApiError",
    "StationSyncResult",
    "StatusSyncResult",
    "main",
    "parse_zcodes",
]


def parse_zcodes(raw: str) -> list[str]:
    """``"12, 51"`` → ``["12", "51"]``. 빈 항목은 버린다."""
    return [code.strip() for code in raw.split(",") if code.strip()]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m evcharge.sync",
        description="한국환경공단 충전소 정보를 받아 공유 캐시(charger_cache)를 채운다.",
    )
    parser.add_argument(
        "--states",
        action="store_true",
        help="전체 재수집 대신 상태만 갱신한다 (호출 1~2건).",
    )
    parser.add_argument(
        "--period",
        type=int,
        default=10,
        help="--states일 때 최근 몇 분 안의 변경분을 받을지 (1~10, 기본 10).",
    )
    parser.add_argument(
        "--zcodes",
        default=None,
        help="수집 대상 시도 코드. 쉼표 구분. 기본값은 설정의 CHARGER_ZCODES.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx는 INFO로 "HTTP Request: GET <전체 URL>"을 찍는다. 그 URL 쿼리에
    # serviceKey가 들어 있어서 터미널과 로그 파일에 인증키가 그대로 남는다.
    # (실제로 한 번 새는 것을 보고 막았다.) 경고 이상만 남긴다.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = get_settings()
    if not settings.charger_api_key:
        # 아무것도 하지 않고 끝낸다. 0으로 끝내면 cron이 "수집되고 있다"고
        # 착각하므로 실패로 알린다.
        logger.error(
            "CHARGER_API_KEY가 비어 있어 수집하지 않았습니다. "
            "backend/.env에 공공데이터포털 인증키를 넣으세요 "
            "(https://www.data.go.kr/data/15076352/openapi.do)."
        )
        return 1

    zcodes = parse_zcodes(args.zcodes if args.zcodes is not None else settings.charger_zcodes)
    if not zcodes:
        logger.error("수집 대상 시도 코드가 비어 있습니다 (CHARGER_ZCODES).")
        return 1

    api = ChargerApiClient(service_key=settings.charger_api_key)

    try:
        with session_scope() as session:
            if args.states:
                states = sync_states(session, api, zcodes, period=args.period)
                logger.info(
                    "상태 갱신 완료: %d행 → 충전소 %d곳 / 충전기 %d대 (캐시에 없는 행 %d)",
                    states.api_rows,
                    states.stations_updated,
                    states.chargers_updated,
                    states.unknown_rows,
                )
            else:
                full = sync_stations(session, api, zcodes)
                logger.info(
                    "전체 수집 완료: %d행 → 충전소 %d곳 / 충전기 %d대 (건너뛴 행 %d)",
                    full.api_rows,
                    full.stations,
                    full.chargers,
                    full.dropped_rows,
                )
    except ChargerApiError as exc:
        # 문구에는 서비스키가 들어 있지 않다 (charger_api._mask).
        logger.error("공공 API 호출 실패: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

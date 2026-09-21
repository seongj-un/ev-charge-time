"""``POST /api/recommend``와 ``POST /api/me/plans``가 함께 쓰는 추천 계산.

``routes/recommend.py``의 ``recommend()`` 라우터 함수 안에 인라인으로 있던 계산
로직(``ChargeRequest`` 생성 → ``price_at``에 대한 ``price_fn`` 클로저 →
``domain.planner.recommend`` 호출 → ``RecommendResponse``로 매핑)을 그대로
옮겨온 것이다.

F-13(충전 기록 저장)은 클라이언트가 보낸 추천 결과를 신뢰하지 않고 서버가
같은 계산을 다시 해서 저장해야 한다. 그 "같은 계산"이 라우터 함수 안에 갇혀
있으면 재사용할 수 없어서 이 모듈로 뺐다.

(C-3, 후속 정리 완료) ``routes/recommend.py``의 ``recommend()``는 이제 이
모듈의 ``compute_recommendation``에 위임한다. vehicle_id 해석(로그인 확인,
본인 차량 조회, 기본값 병합)은 DB 세션이 필요해 라우터 쪽에 남아 있고, 여기
``vehicle_id is not None`` 분기는 ``compute_recommendation``이 세션 없이
직접 호출됐을 때(F-13처럼 vehicle_id를 아직 지원하지 않는 호출자)를 위한
방어선이다 — 라우터는 호출 전에 항상 vehicle_id를 지운 payload를 넘긴다.
"""

from __future__ import annotations

from fastapi import HTTPException

from ..domain.errors import TariffNotConfiguredError
from ..domain.planner import ChargePlan, ChargeRequest
from ..domain.planner import recommend as plan_recommend
from ..domain.pricing import price_at
from ..domain.tariff import Tariff
from .deps import get_holidays, get_tariff
from .schemas import ChargePlanOut, RecommendRequest, RecommendResponse


def compute_recommendation(
    payload: RecommendRequest, tariff: Tariff | None = None
) -> RecommendResponse:
    """요청을 검증하고 최저 비용 충전 구간을 계산해 ``RecommendResponse``로 돌려준다.

    ``tariff``를 넘기면 그 요금 설정을 쓴다 (호출자가 이미 로드해서 버전
    문자열도 같이 써야 할 때 — 예: F-13 저장 시 ``tariff_version``). 넘기지
    않으면 ``get_tariff()``(``lru_cache``)로 직접 가져온다.
    """
    if payload.vehicle_id is not None:
        # F-12 차량 연동은 인증 구현 이후. 계약만 확정해 둔다.
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    if payload.battery_kwh is None or payload.charger_kw is None:
        raise TariffNotConfiguredError(
            "battery_kwh와 charger_kw가 필요합니다. "
            "로그인 후 vehicle_id로 차량 기본값을 쓸 수 있습니다."
        )

    if tariff is None:
        tariff = get_tariff()
    holidays = get_holidays()

    request = ChargeRequest(
        battery_kwh=payload.battery_kwh,
        soc_now=payload.soc_now,
        soc_target=payload.soc_target,
        charger_kw=payload.charger_kw,
        earliest_start=payload.earliest_start,
        deadline=payload.deadline,
        mode=payload.mode,
        public_base_price=payload.public_base_price,
        efficiency=payload.efficiency,
    )

    def price_fn(moment):
        return price_at(moment, payload.mode, tariff, holidays, payload.public_base_price)

    result = plan_recommend(request, price_fn)

    return RecommendResponse(
        best=_to_out(result.best),
        baseline_now=_to_out(result.baseline_now),
        savings_won=result.savings_won,
        candidates_checked=result.candidates_checked,
        assumptions=result.assumptions,
        unverified_tariff_items=tariff.unverified_items(),
    )


def _to_out(plan: ChargePlan) -> ChargePlanOut:
    return ChargePlanOut(**vars(plan))

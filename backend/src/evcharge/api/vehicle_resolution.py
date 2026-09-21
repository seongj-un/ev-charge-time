"""F-12 차량 연동: vehicle_id로 요청 기본값을 채우는 공용 로직.

``POST /api/recommend``와 ``POST /api/me/plans``(3번 수정으로 vehicle_id를
받기 시작한다) 양쪽이 "본인 차량 조회(아니면 404) →
battery_kwh/charger_kw/mode 기본값 병합"을 거의 똑같이 해야 해서 여기
하나로 모은다. 로그인 확인(``current_user``)은 호출자 책임으로 남긴다 —
``/api/recommend``는 vehicle_id가 있을 때만 로그인이 필요하지만
``/api/me/plans``는 애초에 전 엔드포인트가 로그인을 요구해 이미 ``user``를
갖고 있으므로, 여기서 다시 ``current_user``를 부르면 중복 조회가 된다.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession

from ..infra.models import User, Vehicle
from .schemas import RecommendRequest


def resolve_vehicle_defaults(
    payload: RecommendRequest, user: User, session: DbSession
) -> tuple[RecommendRequest, str | None]:
    """vehicle_id가 있으면 본인 차량인지 확인하고 기본값을 병합한 payload와
    그 차량 이름(``saved_plans.vehicle_name`` 스냅샷용)을 함께 돌려준다.
    vehicle_id가 없으면 ``(payload, None)``을 그대로 돌려준다(직접 입력).

    병합한 뒤에는 ``payload.vehicle_id``를 ``None``으로 지운다 —
    ``compute_recommendation``이 이미 해석된 vehicle_id를 다시 보면 미해석
    상태로 오인해 401을 낸다(``recommend_service.py``의 방어선 참고).
    """
    if payload.vehicle_id is None:
        return payload, None

    vehicle = session.get(Vehicle, payload.vehicle_id)
    if vehicle is None or vehicle.user_id != user.id:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")

    updates: dict[str, object] = {"vehicle_id": None}
    if payload.battery_kwh is None:
        updates["battery_kwh"] = vehicle.battery_kwh
    if payload.charger_kw is None:
        updates["charger_kw"] = vehicle.charger_kw
    if "mode" not in payload.model_fields_set:
        updates["mode"] = vehicle.mode
    payload = payload.model_copy(update=updates)

    return payload, vehicle.name

from fastapi import APIRouter, HTTPException, Request

from ...infra.db import session_scope
from ...infra.models import Vehicle
from ..auth_deps import current_user
from ..recommend_service import compute_recommendation
from ..schemas import RecommendRequest, RecommendResponse

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend(payload: RecommendRequest, request: Request) -> RecommendResponse:
    """계산 자체는 ``recommend_service.compute_recommendation``에 위임한다(C-3).

    vehicle_id 해석(로그인 확인, 본인 차량 조회, 기본값 병합)은 DB 세션이
    필요해 여기 라우터에 남긴다 — ``compute_recommendation``은 세션을 받지
    않는 순수 계산 함수라서 F-13(충전 기록 저장, vehicle_id 미지원)에서도
    그대로 재사용할 수 있다. vehicle_id를 이미 해석한 뒤에는 그 결과를 담은
    payload를 그대로 계산 서비스에 넘긴다.

    세션은 ``Depends(get_session)``이 아니라 ``session_scope``로 vehicle_id가
    있을 때만 연다(1번 수정) — ``Depends()``는 요청마다 무조건 해석되므로 그걸
    쓰면 로그인도 DB도 필요 없는 게스트 추천(F-01·F-03·F-04, 이 서비스의 핵심
    기능)까지 Postgres 커넥션에 묶여서, DB가 내려가면 같이 죽고 쓰지도 않는
    커넥션을 매번 풀에서 빌리게 된다. ``/api/timeline``·``/health``처럼 DB가
    필요 없는 요청은 DB와 완전히 무관해야 한다.
    """
    if payload.vehicle_id is not None:
        # F-12 차량 연동: 로그인 필요, 본인 차량이 아니면 404.
        # 요청에 명시된 값(battery_kwh/charger_kw/mode)이 차량 기본값보다 우선한다.
        with session_scope(request.app.dependency_overrides) as session:
            user = current_user(request, session)
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

    return compute_recommendation(payload)

"""확장 기능 라우터.

F-09(태양광 발전 예측)는 아직 스텁이고, F-10(자연어 질의)은 구현됐다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.db import get_session
from ...infra.llm import GeminiClient, LlmClient, LlmError
from ...infra.models import ChatRateLimit, User, Vehicle
from ...settings import get_settings
from .. import chat_service
from ..auth_deps import current_user
from ..recommend_service import compute_recommendation
from ..schemas import ChatRequest, ChatResponse, RecommendRequest, SolarForecast
from ..vehicle_resolution import resolve_vehicle_defaults
from ._stub import not_implemented

router = APIRouter(prefix="/api", tags=["extensions"])


def gemini_api_key() -> str:
    """설정의 Gemini API 키.

    의존성으로 빼 둔 이유는 ``chargers.charger_api_key``와 같다 — 테스트가
    ``dependency_overrides``로 "키 있음/없음"을 직접 정할 수 있어야 하고,
    개발자 ``.env``에 키가 있느냐에 따라 테스트 결과가 갈리면 안 된다.
    """
    return get_settings().gemini_api_key


def llm_client() -> LlmClient:
    """실제 호출기. 테스트는 여기에 가짜를 꽂는다.

    ``GeminiClient``는 SDK 클라이언트를 첫 호출에서야 만들기 때문에, 키가
    없어도 이 의존성 해석 자체는 안전하다 — 아래 핸들러가 501로 끊는 것이
    먼저다.
    """
    settings = get_settings()
    return GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)


@router.get("/solar-forecast", response_model=SolarForecast)
def solar_forecast(region: str, day: date):
    """F-09 태양광 발전 예측 (확장). 기상청 단기예보 + 전력거래소 발전량."""
    return not_implemented("태양광 발전 예측")()


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
    api_key: str = Depends(gemini_api_key),
    client: LlmClient = Depends(llm_client),
) -> ChatResponse:
    """F-10 자연어 질의 (확장). 로그인 필요, 사용자별 호출 제한 초과 시 429.

    순서가 의미를 갖는다: 로그인(401) → 키 없음(501) → 호출 제한(429) → 모델 호출.
    키가 없으면 애초에 부를 수 없으니 할당량을 깎지 않는다.
    """
    if not api_key:
        # settings.py가 약속한 대로 501을 유지한다 — 키 없이도 나머지 기능은
        # 그대로 돌아야 하므로 기동 시점에 막지 않는다 (charger_api_key와 같은 규칙).
        raise HTTPException(
            status_code=501,
            detail="자연어 질의는 아직 준비되지 않았습니다. (Gemini API 키 미설정)",
        )

    now = datetime.now(KST)
    _consume_quota(session, user, now)

    try:
        conditions = chat_service.extract_conditions(
            client, payload.message, now, payload.history
        )
    except LlmError as exc:
        # 모델 쪽 사정이지 요청 잘못이 아니다. 문구에 내부 사정을 싣지 않는다
        # (예외 메시지는 서버 로그용이고, 사용자에게는 다시 시도하라고만 한다).
        raise HTTPException(
            status_code=503,
            detail="지금은 질문에 답할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    default_vehicle = _default_vehicle(session, user)

    def build(request: RecommendRequest):
        """차량 기본값 병합(F-12) → 추천 계산(F-03). 둘 다 재사용이지 재구현이 아니다."""
        if default_vehicle is not None:
            # vehicle_id를 세워 넣어 ``resolve_vehicle_defaults``의 병합 규칙을
            # 그대로 쓴다 — battery_kwh/charger_kw/mode 중 비어 있는 것만 채우고
            # vehicle_id를 다시 지우는 것까지 한 곳에 있다. 본인 차량이므로
            # 소유권 확인은 자명하게 통과한다.
            request = request.model_copy(update={"vehicle_id": default_vehicle.id})
            request, _name = resolve_vehicle_defaults(request, user, session)

        if request.battery_kwh is None or request.charger_kw is None:
            # 아직도 비었다 = 되물어야 한다. compute_recommendation에 넘기면
            # 422가 되는데, 자연어 질의에서는 오류 대신 되묻는 편이 맞다.
            return None, request
        return compute_recommendation(request), request

    return chat_service.answer(
        conditions,
        has_default_vehicle=default_vehicle is not None,
        build_recommendation=build,
        now=now,
    )


# ---------------------------------------------------------------------------
# 사용자별 호출 제한
# ---------------------------------------------------------------------------


def _consume_quota(session: DbSession, user: User, now: datetime) -> None:
    """이번 요청분을 원자적으로 차감하고, 넘었으면 429.

    ``login_attempts.failed_count``와 같은 함정이 있는 자리다. 파이썬에서
    "읽고 → +1 → 쓰기"를 하면 ``get_session()``이 요청마다 새 커넥션을 여는
    구조(기본 READ COMMITTED)에서 병렬 요청들이 같은 값을 읽고 같은 값을
    덮어써 증가분이 사라진다(lost update) — 순차 N회는 막히는데 병렬 N회는
    안 막히는 버그가 된다. 그래서 여기도 UPSERT **한 문장**으로 끝낸다.
    Postgres가 대상 행에 잠금을 걸고 동시 요청을 직렬화하므로, 애플리케이션이
    값을 보지 않고도 증가가 원자적으로 반영된다.

    ``CASE``가 추가로 하는 일: 저장된 창이 이번 요청의 창과 다르면(창이 넘어갔다)
    +1이 아니라 1로 되돌린다. 덕분에 사용자당 행이 하나로 유지되어, 지난 창의
    행을 따로 청소할 필요가 없다.

    **모델을 부르기 전에 커밋한다.** 나중에 세면 호출이 실패한 요청은 공짜가
    되어, 계속 실패시키는 것만으로 제한을 우회할 수 있다 — 실패한 호출도 무료
    티어 할당량은 그대로 깎는다.
    """
    settings = get_settings()
    window = timedelta(minutes=settings.chat_rate_limit_window_minutes)
    window_start = _window_start(now, window)

    increment = (
        pg_insert(ChatRateLimit)
        .values(user_id=user.id, window_start=window_start, used_count=1)
        .on_conflict_do_update(
            index_elements=[ChatRateLimit.user_id],
            set_={
                # 왼쪽 ChatRateLimit.*는 '이미 저장된 행', window_start는
                # '이번 요청의 창'이라는 바인드 값이다.
                "used_count": case(
                    (ChatRateLimit.window_start == window_start, ChatRateLimit.used_count + 1),
                    else_=1,
                ),
                "window_start": window_start,
            },
        )
        .returning(ChatRateLimit.used_count)
    )
    used = session.execute(increment).scalar_one()
    session.commit()

    if used > settings.chat_rate_limit_count:
        raise HTTPException(
            status_code=429,
            detail=(
                f"질문 횟수 제한({settings.chat_rate_limit_window_minutes}분당 "
                f"{settings.chat_rate_limit_count}회)을 초과했습니다. "
                "잠시 후 다시 시도해 주세요."
            ),
        )


def _window_start(now: datetime, window: timedelta) -> datetime:
    """``now``가 속한 고정 창의 시작 시각.

    에폭 기준으로 내림한다 — 창 길이를 설정으로 바꿔도(30분, 2시간 …) 같은
    식이 그대로 통하고, 서버 재시작과 무관하게 경계가 고정된다.
    """
    epoch = datetime(1970, 1, 1, tzinfo=KST)
    return epoch + (now - epoch) // window * window


def _default_vehicle(session: DbSession, user: User) -> Vehicle | None:
    """로그인 사용자의 기본 차량 (F-12). 사용자당 최대 1대다.

    기본 차량이 아닌 차는 쓰지 않는다 — 여러 대 중 어느 차로 묻는 것인지
    질문만으로는 알 수 없고, 아무 차나 골라 쓰면 사용자가 말하지 않은 값으로
    계산한 계획을 받는다.
    """
    return session.scalar(
        select(Vehicle).where(Vehicle.user_id == user.id, Vehicle.is_default.is_(True))
    )

from fastapi import HTTPException

NOT_IMPLEMENTED = 501


def not_implemented(feature: str):
    """계약은 확정하되 본문은 아직 없는 엔드포인트.

    /docs가 전체 API를 보여줘야 프론트가 백엔드를 기다리지 않고 붙을 수 있다.
    """

    def handler(*args, **kwargs):
        raise HTTPException(
            status_code=NOT_IMPLEMENTED,
            detail=f"{feature}은(는) 아직 구현되지 않았습니다.",
        )

    return handler

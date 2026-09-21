"""F-12 내 차량. 사용자당 기본 차량은 최대 1대(``uq_vehicles_one_default_per_user``)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from ...infra.db import get_session
from ...infra.models import User, Vehicle
from ..auth_deps import current_user
from ..schemas import VehicleIn, VehicleOut, VehicleUpdate

router = APIRouter(prefix="/api/me/vehicles", tags=["vehicles"])


def _to_out(vehicle: Vehicle) -> VehicleOut:
    return VehicleOut(
        id=vehicle.id,
        name=vehicle.name,
        battery_kwh=vehicle.battery_kwh,
        charger_kw=vehicle.charger_kw,
        mode=vehicle.mode,
        is_default=vehicle.is_default,
    )


def _get_owned_vehicle(session: DbSession, vehicle_id: str, user: User) -> Vehicle:
    vehicle = session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != user.id:
        # 다른 사용자의 차량도 없는 것과 동일하게 404 (403 아님)
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")
    return vehicle


def _clear_existing_default(
    session: DbSession, user_id: str, *, except_vehicle_id: str | None = None
) -> None:
    """기존 기본 차량을 해제하고 flush.

    부분 유니크 인덱스(uq_vehicles_one_default_per_user)에 걸리지 않으려면
    새 기본 차량을 설정하기 전에, 같은 트랜잭션 안에서 먼저 해제·flush해야 한다.
    """
    stmt = update(Vehicle).where(
        Vehicle.user_id == user_id, Vehicle.is_default.is_(True)
    )
    if except_vehicle_id is not None:
        stmt = stmt.where(Vehicle.id != except_vehicle_id)
    session.execute(stmt.values(is_default=False))
    session.flush()


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> list[VehicleOut]:
    vehicles = session.scalars(
        select(Vehicle).where(Vehicle.user_id == user.id).order_by(Vehicle.created_at)
    ).all()
    return [_to_out(v) for v in vehicles]


@router.post("", response_model=VehicleOut, status_code=201)
def create_vehicle(
    payload: VehicleIn,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> VehicleOut:
    """is_default: true로 등록하면 기존 기본 차량은 자동 해제."""
    if payload.is_default:
        _clear_existing_default(session, user.id)

    vehicle = Vehicle(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name=payload.name,
        battery_kwh=payload.battery_kwh,
        charger_kw=payload.charger_kw,
        mode=payload.mode,
        is_default=payload.is_default,
    )
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    return _to_out(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdate,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> VehicleOut:
    """부분 갱신(C-2): 요청에 실제로 실린 필드만 반영한다.

    ``VehicleIn``을 그대로 받던 이전 버전은 ``is_default``·``mode``에 기본값이
    있어서, 예를 들어 이름만 바꾸려고 그 필드들을 빼고 보내면 기본값(False,
    "self_low")이 그대로 실려 기존 기본 차량이 조용히 해제됐다.
    ``exclude_unset=True``로 실제로 실린 필드만 골라내면 이 문제가 사라진다.
    """
    vehicle = _get_owned_vehicle(session, vehicle_id, user)
    updates = payload.model_dump(exclude_unset=True)

    if updates.get("is_default") is True:
        _clear_existing_default(session, user.id, except_vehicle_id=vehicle.id)

    for field_name, value in updates.items():
        setattr(vehicle, field_name, value)

    session.commit()
    session.refresh(vehicle)
    return _to_out(vehicle)


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(
    vehicle_id: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> None:
    vehicle = _get_owned_vehicle(session, vehicle_id, user)
    session.delete(vehicle)
    session.commit()

"""add car departures

Revision ID: b8d4f2a6c913
Revises: e5c8a3d9f1b2
Create Date: 2026-11-15 21:00:00.000000

출발 시각 학습(BE-8)의 기록 테이블. 새 테이블만 만든다. 되돌리면 출발 기록만 사라진다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8d4f2a6c913'
down_revision: Union[str, Sequence[str], None] = 'e5c8a3d9f1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'car_departures',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('device_id', sa.String(length=36), nullable=False),
        sa.Column('departed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('observed', 'stated')", name='ck_car_departures_source'
        ),
        sa.ForeignKeyConstraint(['device_id'], ['car_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_car_departures_device_departed', 'car_departures', ['device_id', 'departed_at']
    )
    op.create_index(
        'ix_car_departures_device_recorded', 'car_departures', ['device_id', 'recorded_at']
    )
    op.create_index('ix_car_departures_departed', 'car_departures', ['departed_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_car_departures_departed', table_name='car_departures')
    op.drop_index('ix_car_departures_device_recorded', table_name='car_departures')
    op.drop_index('ix_car_departures_device_departed', table_name='car_departures')
    op.drop_table('car_departures')

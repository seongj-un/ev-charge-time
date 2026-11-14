"""add car devices and savings (와트잇 BE-5 절약 리포트)

차량 앱(로그인 없음)의 기기 토큰, 절감 기록, 기기 발급 IP별 속도 제한.
세 테이블 모두 새로 만들기만 해서 기존 테이블에 잠금이 걸리지 않는다.
되돌리면 세 테이블이 통째로 사라진다 (기기 토큰과 절감 기록도 함께).

Revision ID: c4e8a1f2b7d3
Revises: e557028bf5dd
Create Date: 2026-11-15 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1f2b7d3'
down_revision: Union[str, Sequence[str], None] = 'e557028bf5dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'car_devices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_table(
        'car_savings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('device_id', sa.String(length=36), nullable=False),
        sa.Column('cause', sa.String(length=10), nullable=False),
        sa.Column('savings_won', sa.Integer(), nullable=False),
        sa.Column('energy_kwh', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("cause IN ('time', 'payment')", name='ck_car_savings_cause'),
        sa.CheckConstraint("source IN ('plan', 'leak_check')", name='ck_car_savings_source'),
        sa.CheckConstraint('savings_won >= 0 AND savings_won <= 100000', name='ck_car_savings_won_range'),
        sa.ForeignKeyConstraint(['device_id'], ['car_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_car_savings_device_confirmed', 'car_savings', ['device_id', 'confirmed_at'], unique=False)
    op.create_index('ix_car_savings_device_created', 'car_savings', ['device_id', 'created_at'], unique=False)
    op.create_table(
        'car_device_rate_limits',
        sa.Column('ip_hash', sa.String(length=64), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('ip_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('car_device_rate_limits')
    op.drop_index('ix_car_savings_device_created', table_name='car_savings')
    op.drop_index('ix_car_savings_device_confirmed', table_name='car_savings')
    op.drop_table('car_savings')
    op.drop_table('car_devices')

"""add car voice quotas

Revision ID: d7b2e9c41a68
Revises: c4e8a1f2b7d3
Create Date: 2026-11-15 12:00:00.000000

와트잇 음성 대화(BE-3)의 기기별·서비스 전체 하루 카운터. 새 테이블만 만들어 기존
테이블에 잠금이 걸리지 않는다. 되돌리면 두 카운터 테이블이 사라진다(카운터라 잃을
데이터가 없다).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7b2e9c41a68'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1f2b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'car_voice_rate_limits',
        sa.Column('device_id', sa.String(length=36), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['car_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('device_id'),
    )
    op.create_table(
        'car_voice_service_quota',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('car_voice_service_quota')
    op.drop_table('car_voice_rate_limits')

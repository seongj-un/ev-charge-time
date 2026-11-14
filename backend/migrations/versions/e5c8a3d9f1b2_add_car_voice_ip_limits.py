"""add car voice ip limits

Revision ID: e5c8a3d9f1b2
Revises: d7b2e9c41a68
Create Date: 2026-11-15 15:00:00.000000

음성 대화(BE-3)의 IP별 하루 카운터. 새 테이블만 만든다. 되돌리면 이 카운터만 사라진다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5c8a3d9f1b2'
down_revision: Union[str, Sequence[str], None] = 'd7b2e9c41a68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'car_voice_ip_limits',
        sa.Column('ip_hash', sa.String(length=64), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('ip_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('car_voice_ip_limits')

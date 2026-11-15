"""add charger sync state

Revision ID: a9e4c2f7b3d1
Revises: f2a7c5e8d104
Create Date: 2026-11-15 15:00:00.000000

충전기 상태 신선도(BE-10)의 "여기까지 확인했다" 시각. 새 테이블만 만든다. 되돌리면 상태
시각은 charger_cache.updated_at만으로 계산된다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9e4c2f7b3d1'
down_revision: Union[str, Sequence[str], None] = 'f2a7c5e8d104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'charger_sync_state',
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('kind'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('charger_sync_state')

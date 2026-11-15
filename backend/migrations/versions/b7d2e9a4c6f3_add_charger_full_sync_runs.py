"""add charger full sync runs

Revision ID: b7d2e9a4c6f3
Revises: a9e4c2f7b3d1
Create Date: 2026-11-15 17:00:00.000000

BE-10 리뷰 반영: 상태 수집이 끊기면 전체 수집으로 확인 시각을 되살리는데, 그 하루 횟수를
세는 기록. 새 테이블만 만든다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e9a4c6f3"
down_revision: Union[str, Sequence[str], None] = "a9e4c2f7b3d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "charger_full_sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("recovery", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("charger_full_sync_runs")

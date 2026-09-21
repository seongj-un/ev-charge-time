"""add chat_rate_limits

Revision ID: b31c7a04f5e2
Revises: 9862b7e5d249
Create Date: 2026-09-21 23:40:00.000000

F-10 자연어 질의의 사용자별 호출 제한(명세: 초과 시 429). 사용자당 한 행이고,
한 문장짜리 UPSERT가 "같은 창이면 +1, 창이 넘어갔으면 1로 초기화"를 원자적으로
처리한다 — login_attempts.failed_count를 읽고-쓰다 병렬 요청에 증가분을
잃어버렸던 것(lost update)을 되풀이하지 않기 위해서다.

users.id를 ondelete CASCADE로 물린다: 탈퇴한 사용자의 잔여 카운터를 따로
지워줄 필요가 없다.

기존 마이그레이션들과 같은 처리: autogenerate가
favorite_stations.uq_favorite_user_station을 매번 "추가됨"으로 잡는 오탐이
있어(Postgres가 그 이름을 복합 PK 인덱스에 합쳤다) 그 항목은 걷어냈다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b31c7a04f5e2'
down_revision: Union[str, Sequence[str], None] = '9862b7e5d249'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_rate_limits',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('chat_rate_limits')

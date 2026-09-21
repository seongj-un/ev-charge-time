"""add charge_start to saved_plans

Revision ID: 2817d8a3e458
Revises: 040d67ec4d97
Create Date: 2026-09-21 19:50:55.058331

충전 시작 시각(= result["best"]["start"])을 컬럼으로 뽑는다. 월 필터와 목록
정렬이 이 컬럼을 기준으로 하기 때문이다(4번 수정).

기존 행은 result JSONB에서 백필한다 — 안 하면 not null 제약에 걸리고, 설령
nullable로 두더라도 기존 기록이 월 필터에서 통째로 사라진다. 그래서 컬럼을
nullable로 추가 → 백필 → not null로 조인다.

autogenerate가 favorite_stations.uq_favorite_user_station을 매번 "추가됨"으로
잡는 오탐이 있어(Postgres가 그 이름의 UniqueConstraint를 복합 PK 인덱스에
합쳐버렸다) 그 항목은 걷어냈다. 기존 마이그레이션들도 같은 처리를 했다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2817d8a3e458'
down_revision: Union[str, Sequence[str], None] = '040d67ec4d97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'saved_plans',
        sa.Column('charge_start', sa.DateTime(timezone=True), nullable=True),
    )

    # 기존 행 백필. result->'best'->>'start'는 "2026-10-07T22:00:00+09:00"
    # 형태의 ISO 문자열이라 timestamptz로 그대로 캐스팅된다.
    op.execute(
        """
        UPDATE saved_plans
        SET charge_start = (result->'best'->>'start')::timestamptz
        WHERE charge_start IS NULL
        """
    )

    op.alter_column('saved_plans', 'charge_start', nullable=False)
    op.create_index(
        op.f('ix_saved_plans_charge_start'),
        'saved_plans',
        ['charge_start'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_saved_plans_charge_start'), table_name='saved_plans')
    op.drop_column('saved_plans', 'charge_start')

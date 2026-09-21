"""add lat lng to charger_cache

Revision ID: 9862b7e5d249
Revises: 72f0519a6232
Create Date: 2026-09-21 21:49:18.911776

좌표를 data JSONB에서 컬럼으로 꺼내고 복합 인덱스를 건다(F-07). 반경 조회의
1차 필터가 매 요청 JSONB를 캐스팅하면 인덱스를 못 타고 3만 건을 통째로 훑는다
— saved_plans.charge_start를 컬럼으로 뽑았던 것과 같은 이유다.

백필은 없다. 적용 시점의 charger_cache는 0행이고(수집기가 이번에 처음
채운다), 좌표를 모르는 행은 반경 조회에 잡히지 않을 뿐 즐겨찾기 조회(F-14)는
그대로 동작하므로 nullable로 둔다.

autogenerate가 favorite_stations.uq_favorite_user_station을 매번 "추가됨"으로
잡는 오탐이 있어(Postgres가 그 이름의 UniqueConstraint를 복합 PK 인덱스에
합쳐버렸다) 그 항목은 걷어냈다. 기존 마이그레이션들도 같은 처리를 했다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9862b7e5d249'
down_revision: Union[str, Sequence[str], None] = '72f0519a6232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('charger_cache', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('charger_cache', sa.Column('lng', sa.Float(), nullable=True))
    op.create_index(
        'ix_charger_cache_lat_lng', 'charger_cache', ['lat', 'lng'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_charger_cache_lat_lng', table_name='charger_cache')
    op.drop_column('charger_cache', 'lng')
    op.drop_column('charger_cache', 'lat')

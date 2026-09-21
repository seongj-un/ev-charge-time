"""add vehicle_name snapshot to saved_plans

Revision ID: 040d67ec4d97
Revises: 706dae45ad3f
Create Date: 2026-09-21 17:35:14.670433

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '040d67ec4d97'
down_revision: Union[str, Sequence[str], None] = '706dae45ad3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # autogenerate가 이번에도 favorite_stations.uq_favorite_user_station을
    # "추가"로 오탐했다(a7973d494694, 706dae45ad3f에서와 같은 오탐 — 그 제약은
    # PK와 같은 컬럼이라 Postgres가 PK 인덱스에 합쳐서 이미 존재한다). 그
    # create_unique_constraint 라인은 지웠다. 실제로 필요한 변경은 nullable
    # 컬럼 추가 하나뿐이다 — 요금이 바뀌어도 재계산하지 않으려고
    # tariff_version을 스냅샷으로 박아둔 것과 같은 이유로, 저장 당시 차량
    # 이름도 스냅샷으로 남긴다(3번 수정). nullable이라 기존 행은 그냥 null이
    # 된다.
    op.add_column('saved_plans', sa.Column('vehicle_name', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('saved_plans', 'vehicle_name')

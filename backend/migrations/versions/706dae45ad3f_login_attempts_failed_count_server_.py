"""login_attempts failed_count server default

Revision ID: 706dae45ad3f
Revises: a7973d494694
Create Date: 2026-09-21 16:51:57.212404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '706dae45ad3f'
down_revision: Union[str, Sequence[str], None] = 'a7973d494694'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # autogenerate가 낸 원안은 favorite_stations.uq_favorite_user_station를
    # "추가"로 오탐했다 — 그 제약은 초기 마이그레이션(9040fea9add1)에서 PK와 같은
    # 컬럼이라 Postgres가 PK 인덱스에 합쳐서 이미 존재한다(a7973d494694에서도 같은
    # 오탐을 겪었다). 그 라인은 지웠다.
    #
    # 반대로 이번에 실제로 필요한 변경(server_default 추가)은 autogenerate가 잡지
    # 못했다 — env.py가 compare_server_default를 켜두지 않아서 서버 기본값만
    # 바뀌는 건 기본적으로 비교 대상이 아니다. 그래서 아래 alter_column은 손으로 썼다.
    op.alter_column(
        "login_attempts",
        "failed_count",
        server_default=sa.text("0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "login_attempts",
        "failed_count",
        server_default=None,
    )

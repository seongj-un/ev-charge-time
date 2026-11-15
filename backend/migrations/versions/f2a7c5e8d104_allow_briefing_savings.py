"""allow briefing as a car saving source

Revision ID: f2a7c5e8d104
Revises: b8d4f2a6c913
Create Date: 2026-11-15 23:30:00.000000

시동 ON 브리핑(BE-9)이 만드는 대기 절감 기록의 출처 ``briefing``을 허용한다. 제약만 바꾼다.
되돌리면 ``briefing`` 기록은 같은 계산(BE-1 충전 계획)에서 나온 ``plan``으로 바뀐다. 지우면
확정된 절감 합계가 줄어든다.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f2a7c5e8d104'
down_revision: Union[str, Sequence[str], None] = 'b8d4f2a6c913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_car_savings_source', 'car_savings', type_='check')
    op.create_check_constraint(
        'ck_car_savings_source', 'car_savings', "source IN ('plan', 'leak_check', 'briefing')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE car_savings SET source = 'plan' WHERE source = 'briefing'")
    op.drop_constraint('ck_car_savings_source', 'car_savings', type_='check')
    op.create_check_constraint(
        'ck_car_savings_source', 'car_savings', "source IN ('plan', 'leak_check')"
    )

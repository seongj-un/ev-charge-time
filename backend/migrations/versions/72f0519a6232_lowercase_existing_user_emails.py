"""lowercase existing user emails

Revision ID: 72f0519a6232
Revises: 2817d8a3e458
Create Date: 2026-09-21 20:14:56.182377

I-3: SignupRequest/LoginRequest.email이 이제 저장·조회 양쪽에서 소문자로
정규화된다(schemas.py의 NormalizedEmail). 정규화를 코드에만 넣고 기존 행을
그대로 두면, 대문자가 섞인 이메일로 이미 가입한 사용자는 다음 로그인부터
```email == lower(입력)```이 기존 대소문자 섞인 행과 더 이상 일치하지 않아
로그인이 깨진다 — 그래서 기존 행도 함께 소문자로 맞춘다.

배포 전 개발 DB(evcharge) 확인: 현재 가입된 16개 계정 전부 이미 소문자라
이 UPDATE는 실질적으로 no-op이다(리뷰 시점 기준). 그래도 이 마이그레이션
자체는 다른 환경(로컬 클론, CI, 향후 배포)에 대비한 안전망으로 남겨둔다.

만약 두 행이 소문자로 낮췄을 때 같은 값이 되는 경우(예: "A@x.com"과
"a@x.com"이 둘 다 존재)가 있다면, users.email의 UNIQUE 제약에 걸려 이
UPDATE 자체가 실패하며 마이그레이션이 멈춘다 — 조용히 한쪽 계정을 지우거나
병합하는 대신 실패를 택했다. 그런 충돌은 애초에 이 마이그레이션이 고치려는
"같은 사람이 대소문자 차이로 두 계정을 가진" 상황 그 자체라 자동으로
병합할 방법이 없고(어느 계정의 차량/기록/즐겨찾기를 남길지는 운영자 판단이
필요하다), 배포 전에 드러나는 편이 로그인 시점에 조용히 갈라지는 것보다
낫다는 판단이다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72f0519a6232'
down_revision: Union[str, Sequence[str], None] = '2817d8a3e458'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")


def downgrade() -> None:
    """Downgrade schema.

    소문자화는 원래 대소문자 표기를 보존하지 않으므로 되돌릴 수 없다(정보
    손실). 애초에 대소문자 구분이 버그였으므로 내릴 이유도 없다 — no-op.
    """
    pass

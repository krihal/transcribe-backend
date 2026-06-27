"""merge webauthn and manually_set_notifications

Revision ID: 18bfdf3a5c10
Revises: cc7d1a2e9b4f, d8e1f3a5b7c2
Create Date: 2026-06-27 22:26:47.597204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18bfdf3a5c10'
down_revision: Union[str, Sequence[str], None] = ('cc7d1a2e9b4f', 'd8e1f3a5b7c2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

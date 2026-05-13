# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Add table for notifications.

Revision ID: 0c309fb6c471
Revises: 2f4030b1c1ec
Create Date: 2026-01-06 10:18:05.609031

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0c309fb6c471"
down_revision: Union[str, Sequence[str], None] = "2f4030b1c1ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    engine = op.get_bind()
    inspector = inspect(engine)

    if "notifications_sent" not in inspector.get_table_names():
        op.create_table(
            "notifications_sent",
            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                autoincrement=True,
                nullable=False,
            ),
            sa.Column("user_id", sa.VARCHAR(), nullable=True),
            sa.Column("notification_type", sa.VARCHAR(), nullable=True),
            sa.Column(
                "sent_at",
                sa.TIMESTAMP(),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("uuid", sa.VARCHAR(), nullable=True),
        )
        op.create_index(
            op.f("ix_notifications_sent_user_id"),
            "notifications_sent",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_notifications_sent_uuid"),
            "notifications_sent",
            ["uuid"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""

    engine = op.get_bind()
    inspector = inspect(engine)

    if "notifications_sent" in inspector.get_table_names():
        op.drop_index(
            op.f("ix_notifications_sent_user_id"), table_name="notifications_sent"
        )
        op.drop_index(
            op.f("ix_notifications_sent_uuid"), table_name="notifications_sent"
        )
        op.drop_table("notifications_sent")

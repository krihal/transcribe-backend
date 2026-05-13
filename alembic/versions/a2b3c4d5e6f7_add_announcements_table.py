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

"""Add announcements table.

Revision ID: a2b3c4d5e6f7
Revises: f8b4c6d9e3a2
Create Date: 2026-03-17 00:00:01.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "b2d4e6f8a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_severity_enum(bind: sa.engine.Connection) -> postgresql.ENUM:
    """Create the severity enum type if it doesn't already exist."""
    severity_enum = postgresql.ENUM(
        "info",
        "maintenance",
        "major_incident",
        name="announcementseverityenum",
        create_type=False,
    )

    # SQLite doesn't have native enum types — nothing to create
    if bind.dialect.name == "sqlite":
        return severity_enum

    result = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'announcementseverityenum'")
    )

    if not result.scalar():
        severity_enum.create(bind)

    return severity_enum


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)

    if "announcements" not in inspector.get_table_names():
        severity_enum = _ensure_severity_enum(bind)

        op.create_table(
            "announcements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("message", sa.String(), nullable=False),
            sa.Column(
                "severity",
                severity_enum,
                nullable=False,
                server_default="info",
            ),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by", sa.String(), nullable=True),
        )
    else:
        columns = [c["name"] for c in inspector.get_columns("announcements")]
        if "severity" not in columns:
            severity_enum = _ensure_severity_enum(bind)

            op.add_column(
                "announcements",
                sa.Column(
                    "severity",
                    severity_enum,
                    nullable=False,
                    server_default="info",
                ),
            )


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)

    if "announcements" in inspector.get_table_names():
        op.drop_table("announcements")

    severity_enum = sa.Enum(name="announcementseverityenum")
    severity_enum.drop(bind, checkfirst=True)

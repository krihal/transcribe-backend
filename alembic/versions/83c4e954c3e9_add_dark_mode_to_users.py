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

"""Add dark_mode column to users.

Revision ID: 83c4e954c3e9
Revises: c4d5e6f7a8b9
Create Date: 2026-04-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "83c4e954c3e9"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_dark_mode_enum(bind: sa.engine.Connection) -> sa.Enum:
    """Create the dark_mode enum type if it doesn't already exist."""
    dark_mode_enum = sa.Enum(
        "dark",
        "light",
        "auto",
        name="darkmodeenum",
        create_type=False,
    )

    # SQLite doesn't have native enum types — nothing to create
    if bind.dialect.name == "sqlite":
        return dark_mode_enum

    result = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'darkmodeenum'")
    )

    if not result.scalar():
        dark_mode_enum.create(bind)

    return dark_mode_enum


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [x["name"] for x in inspector.get_columns("users")]

    if "dark_mode" not in columns:
        dark_mode_enum = _ensure_dark_mode_enum(bind)

        op.add_column(
            "users",
            sa.Column(
                "dark_mode",
                dark_mode_enum,
                nullable=False,
                server_default="auto",
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""

    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [x["name"] for x in inspector.get_columns("users")]

    if "dark_mode" in columns:
        op.drop_column("users", "dark_mode")

    dark_mode_enum = sa.Enum(name="darkmodeenum")
    dark_mode_enum.drop(bind, checkfirst=True)

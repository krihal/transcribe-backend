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

"""Add attribute_rules table.

Revision ID: f8b4c6d9e3a2
Revises: e7a3b5c8d2f1
Create Date: 2026-03-12 00:00:01.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f8b4c6d9e3a2"
down_revision: Union[str, Sequence[str], None] = "e7a3b5c8d2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONDITION_VALUES = (
    "EQUALS",
    "NOT_EQUALS",
    "CONTAINS",
    "NOT_CONTAINS",
    "STARTS_WITH",
    "ENDS_WITH",
    "REGEX_MATCH",
)

condition_enum = postgresql.ENUM(
    *CONDITION_VALUES, name="attributeconditionenum", create_type=False
)


def _ensure_condition_enum(bind: sa.engine.Connection) -> postgresql.ENUM:
    """Create the attribute condition enum type if it doesn't already exist."""

    if bind.dialect.name == "sqlite":
        return condition_enum

    result = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'attributeconditionenum'")
    )

    if not result.scalar():
        condition_enum.create(bind)

    return condition_enum


def upgrade() -> None:
    """Upgrade schema."""

    engine = op.get_bind()
    inspector = inspect(engine)

    if "attribute_rules" not in inspector.get_table_names():
        _ensure_condition_enum(engine)

        op.create_table(
            "attribute_rules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(), nullable=False, index=True),
            sa.Column("attribute_name", sa.String(), nullable=False, index=True),
            sa.Column(
                "attribute_condition",
                condition_enum,
                nullable=False,
            ),
            sa.Column("attribute_value", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "activate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "deny",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("assign_to_group", sa.String(), nullable=True),
            sa.Column("assign_to_admin_domains", sa.String(), nullable=True),
            sa.Column("realm", sa.String(), nullable=True, index=True),
            sa.Column("owner_domains", sa.String(), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""

    engine = op.get_bind()
    inspector = inspect(engine)

    if "attribute_rules" in inspector.get_table_names():
        op.drop_table("attribute_rules")

    condition_enum.drop(engine, checkfirst=True)

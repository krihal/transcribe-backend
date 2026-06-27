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

"""Add webauthn_credentials table

Revision ID: cc7d1a2e9b4f
Revises: 67f5afa39d75
Create Date: 2026-06-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy import inspect

revision: str = "cc7d1a2e9b4f"
down_revision: Union[str, Sequence[str], None] = "67f5afa39d75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    engine = op.get_bind()
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "webauthn_credentials" not in tables:
        op.create_table(
            "webauthn_credentials",
            sa.Column("id", sa.INTEGER(), nullable=False),
            sa.Column("user_id", sa.VARCHAR(), nullable=False),
            sa.Column("credential_id", sa.VARCHAR(), nullable=False),
            sa.Column("public_key", sa.VARCHAR(), nullable=False),
            sa.Column("sign_count", sa.INTEGER(), nullable=False, server_default="0"),
            sa.Column("name", sa.VARCHAR(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("credential_id"),
        )
        op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])
        op.create_index("ix_webauthn_credentials_credential_id", "webauthn_credentials", ["credential_id"])


def downgrade() -> None:
    """Downgrade schema."""
    engine = op.get_bind()
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "webauthn_credentials" in tables:
        op.drop_index("ix_webauthn_credentials_credential_id", table_name="webauthn_credentials")
        op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
        op.drop_table("webauthn_credentials")

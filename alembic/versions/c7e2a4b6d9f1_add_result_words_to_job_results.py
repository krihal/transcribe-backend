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

"""Add result_words column to job_results.

Holds the encrypted per-word timing/confidence payload. Nullable with no
backfill: existing rows keep NULL and every existing read path ignores the
column, so results produced before this migration stay readable unchanged.

Revision ID: c7e2a4b6d9f1
Revises: d8e1f3a5b7c2
Create Date: 2026-08-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "c7e2a4b6d9f1"
down_revision: Union[str, Sequence[str], None] = "d8e1f3a5b7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    engine = op.get_bind()
    inspector = inspect(engine)
    columns = [x["name"] for x in inspector.get_columns("job_results")]

    if "result_words" not in columns:
        op.add_column(
            "job_results",
            sa.Column("result_words", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""

    engine = op.get_bind()
    inspector = inspect(engine)
    columns = [x["name"] for x in inspector.get_columns("job_results")]

    if "result_words" in columns:
        op.drop_column("job_results", "result_words")

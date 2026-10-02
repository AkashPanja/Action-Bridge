"""Cloud provider support: extra_headers for gateways (OpenRouter etc.)

Revision ID: 010
Revises: 009
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("llm_providers") as batch_op:
        batch_op.add_column(sa.Column("extra_headers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table("llm_providers") as batch_op:
        batch_op.drop_column("extra_headers")

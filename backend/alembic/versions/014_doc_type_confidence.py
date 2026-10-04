"""Per-document-type auto-approve confidence threshold.

Revision ID: 014
Revises: 013
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_types",
        sa.Column(
            "confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.95",
        ),
    )


def downgrade() -> None:
    op.drop_column("document_types", "confidence_threshold")

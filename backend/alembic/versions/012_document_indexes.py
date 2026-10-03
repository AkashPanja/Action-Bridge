"""Composite indexes for the document inbox query.

Revision ID: 012
Revises: 011
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_documents_project_visible_created",
        "document_instances",
        ["project_id", "is_deleted", "created_at"],
    )
    op.create_index(
        "ix_documents_project_status",
        "document_instances",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_project_status", table_name="document_instances")
    op.drop_index("ix_documents_project_visible_created", table_name="document_instances")

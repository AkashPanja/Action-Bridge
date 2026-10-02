"""M2 extraction pipeline: profiles, submissions, files, document provenance

Revision ID: 009
Revises: 008
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extraction_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="per_attachment"),
        sa.Column("candidate_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("target_document_type_id", sa.String(36), sa.ForeignKey("document_types.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prompts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provider_chain", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("ocr_provider_id", sa.String(36), sa.ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("allow_cloud", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("trigger_id", sa.String(36), nullable=True, index=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("extraction_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_meta", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("api_key_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, index=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "submission_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(1024), nullable=False),
        sa.Column("mime", sa.String(255), nullable=False, server_default="application/octet-stream"),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=False, server_default="", index=True),
        sa.Column("storage_path", sa.String(2048), nullable=False, server_default=""),
        sa.Column("text_path", sa.String(2048), nullable=False, server_default=""),
        sa.Column("text_source", sa.String(20), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("skip_reason", sa.String(255), nullable=True),
        sa.Column("detected_type", sa.String(36), sa.ForeignKey("document_types.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("document_instances.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    with op.batch_alter_table("document_instances") as batch_op:
        batch_op.add_column(sa.Column("submission_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("extraction_meta", sa.JSON(), nullable=True))
        batch_op.create_index("ix_document_instances_submission_id", ["submission_id"])
        batch_op.create_foreign_key(
            "fk_documents_submission", "submissions", ["submission_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("document_instances") as batch_op:
        batch_op.drop_constraint("fk_documents_submission", type_="foreignkey")
        batch_op.drop_index("ix_document_instances_submission_id")
        batch_op.drop_column("extraction_meta")
        batch_op.drop_column("source")
        batch_op.drop_column("submission_id")
    op.drop_table("submission_files")
    op.drop_table("submissions")
    op.drop_table("extraction_profiles")

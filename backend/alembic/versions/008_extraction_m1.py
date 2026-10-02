"""M1 extraction foundations: credentials, providers, processing, jobs, call log

Revision ID: 008
Revises: 007
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("hint", sa.String(50), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "llm_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("base_url", sa.String(1024), nullable=False),
        sa.Column("credential_id", sa.String(36), sa.ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("vision", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("json_schema", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("json_object", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("timeout_s", sa.Float(), nullable=False, server_default="120"),
        sa.Column("is_local", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "processing_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(255), nullable=False, unique=True),
        sa.Column("values", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("submission_id", sa.String(36), nullable=True, index=True),
        sa.Column("kind", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued", index=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "provider_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("local", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("provider_calls")
    op.drop_table("jobs")
    op.drop_table("processing_settings")
    op.drop_table("llm_providers")
    op.drop_table("credentials")

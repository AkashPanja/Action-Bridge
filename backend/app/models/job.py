import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.project import Base

JOB_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "retrying",
    "cancelled",
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Nullable until M2 introduces submissions.
    submission_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True
    )
    # Worker input for the kind handler; result/usage written on completion.
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

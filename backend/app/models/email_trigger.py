import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.project import Base

TRIGGER_TYPES = ("email",)
TRIGGER_MODES = ("per_attachment", "combined")


class EmailTrigger(Base):
    """A saved rule watching one mailbox (FR-6.x). type=email today;
    folder-watcher/scheduler plug in later via TRIGGER_TYPES."""

    __tablename__ = "email_triggers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    credential_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("extraction_profiles.id", ondelete="SET NULL"), nullable=True
    )
    # null = follow the profile's own mode.
    mode_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # config: {folder, poll_interval_s, filters{sender, subject_pattern,
    # body_pattern, must_have_attachment, allowed_types, max_attachment_mb,
    # received_after}, after_action{mark_read, move_to_folder}, import_window}
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # state: {last_uid, initialized, consecutive_failures, alert,
    # last_run_at, last_error, next_due_at}
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TriggerRun(Base):
    """One poll execution of a trigger (FR-6.5 run history)."""

    __tablename__ = "trigger_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    trigger_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("email_triggers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submissions_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_enqueued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

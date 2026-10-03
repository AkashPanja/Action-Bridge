import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.project import Base


class ProcessingSetting(Base):
    __tablename__ = "processing_settings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # "global" or "project:<project_id>"
    scope: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


DEFAULT_PROCESSING = {
    "cpu_workers": 4,
    "max_jobs_in_flight": 8,
    "default_retries": 3,
    "default_timeout_s": 120,
    "paused": False,
    # Extraction auto-approve: documents whose every field scores at or above
    # this are approved without human review (FR-8.1b). 0 disables it.
    "auto_approve_threshold": 0.92,
}

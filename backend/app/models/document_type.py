import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.project import Base


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Auto-approve bar: every REQUIRED schema field must score >= this.
    # Editable per type at creation and later (default 0.95).
    confidence_threshold: Mapped[float] = mapped_column(
        Float, default=0.95, nullable=False, server_default="0.95"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project = relationship("Project", backref="document_types")

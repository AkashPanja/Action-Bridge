import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.project import Base


class DocumentInstance(Base):
    __tablename__ = "document_instances"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    document_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_types.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="received", index=True)
    extracted_data: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Extraction provenance (M2). Null for manually/bot-submitted documents.
    submission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extraction_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project = relationship("Project", backref="document_instances")
    document_type = relationship("DocumentType", backref="document_instances")

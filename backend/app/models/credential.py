import uuid
from datetime import datetime

from sqlalchemy import JSON, String, Text, func
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.project import Base

CREDENTIAL_TYPES = ("api_key", "basic", "oauth2")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Non-secret metadata (host, username, notes). Secrets live ONLY in encrypted_payload.
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    hint: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

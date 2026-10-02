from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class DocumentSubmit(BaseModel):
    extracted_data: dict
    confidence_scores: dict | None = None


class DocumentUpdate(BaseModel):
    extracted_data: dict | None = None
    confidence_scores: dict | None = None
    status: str | None = None
    comment: str | None = None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    action: str
    actor: str
    field_name: str | None
    old_value: dict | None
    new_value: dict | None
    comment: str | None
    timestamp: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_type_id: str
    status: str
    extracted_data: dict
    confidence_score: float | None
    confidence_scores: dict | None
    created_at: datetime
    updated_at: datetime
    history: list[AuditEventResponse] | None = None
    submission_id: str | None = None
    source: str | None = None
    extraction_meta: dict | None = None


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    document_type_id: str
    status: str
    extracted_data: dict
    confidence_score: float | None
    confidence_scores: dict | None
    created_at: datetime
    updated_at: datetime
    document_type_name: str | None = None
    submission_id: str | None = None
    source: str | None = None
    extraction_meta: dict | None = None

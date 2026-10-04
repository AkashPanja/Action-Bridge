from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BulkIds(BaseModel):
    ids: list[str]

from app.utils.json_schema import validate_json_schema


class DocumentTypeCreate(BaseModel):
    name: str
    schema_definition: dict
    validation_rules: dict | None = None
    confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_schema(self):
        errors = validate_json_schema(self.schema_definition)
        if errors:
            raise ValueError(f"Invalid JSON Schema: {', '.join(errors)}")
        return self


class DocumentTypeUpdate(BaseModel):
    name: str | None = None
    schema_definition: dict | None = None
    validation_rules: dict | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class DocumentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    schema_definition: dict
    validation_rules: dict | None
    confidence_threshold: float = 0.95
    created_at: datetime
    updated_at: datetime
    document_count: int | None = None

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_instance import DocumentInstance
from app.models.document_type import DocumentType
from app.schemas.document_type import BulkIds, DocumentTypeCreate, DocumentTypeUpdate
from app.services.project_service import get_project


async def create_document_type(
    db: AsyncSession, project_id: str, data: DocumentTypeCreate
) -> DocumentType | None:
    project = await get_project(db, project_id)
    if not project:
        return None
    doc_type = DocumentType(
        project_id=project_id,
        name=data.name,
        schema_definition=data.schema_definition,
        validation_rules=data.validation_rules,
        confidence_threshold=data.confidence_threshold,
    )
    db.add(doc_type)
    await db.commit()
    await db.refresh(doc_type)
    return doc_type


async def clone_document_type(
    db: AsyncSession, project_id: str, source_type_id: str, new_name: str
) -> DocumentType | None:
    source = await get_document_type(db, source_type_id)
    if not source or source.project_id != project_id:
        return None
    doc_type = DocumentType(
        project_id=project_id,
        name=new_name,
        schema_definition=source.schema_definition,
        validation_rules=source.validation_rules,
        confidence_threshold=source.confidence_threshold,
    )
    db.add(doc_type)
    await db.commit()
    await db.refresh(doc_type)
    return doc_type


async def get_document_type(db: AsyncSession, type_id: str) -> DocumentType | None:
    result = await db.execute(
        select(DocumentType).where(
            DocumentType.id == type_id, DocumentType.is_deleted == False
        )
    )
    return result.scalar_one_or_none()


async def list_document_types(
    db: AsyncSession, project_id: str
) -> list[dict]:
    result = await db.execute(
        select(DocumentType)
        .where(
            DocumentType.project_id == project_id,
            DocumentType.is_deleted == False,
        )
        .order_by(DocumentType.created_at.desc())
    )
    types = list(result.scalars().all())
    if not types:
        return []

    doc_counts = await db.execute(
        select(DocumentInstance.document_type_id, func.count(DocumentInstance.id).label("cnt"))
        .where(
            DocumentInstance.project_id == project_id,
            DocumentInstance.is_deleted == False,
            DocumentInstance.document_type_id.in_([t.id for t in types]),
        )
        .group_by(DocumentInstance.document_type_id)
    )
    count_map = {row.document_type_id: row.cnt for row in doc_counts}

    return [
        {**{k: v for k, v in t.__dict__.items() if k != "_sa_instance_state"}, "document_count": count_map.get(t.id, 0)}
        for t in types
    ]


async def update_document_type(
    db: AsyncSession, type_id: str, data: DocumentTypeUpdate
) -> DocumentType | None:
    doc_type = await get_document_type(db, type_id)
    if not doc_type:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if "schema_definition" in update_data and update_data["schema_definition"] is not None:
        doc_count = await db.scalar(
            select(func.count(DocumentInstance.id)).where(
                DocumentInstance.document_type_id == type_id,
                DocumentInstance.is_deleted == False,
            )
        )
        if doc_count and doc_count > 0:
            old_keys = set((doc_type.schema_definition.get("properties") or {}).keys())
            new_keys = set((update_data["schema_definition"].get("properties") or {}).keys())
            removed = old_keys - new_keys
            if removed:
                raise ValueError(f"Cannot remove fields {sorted(removed)}: documents exist for this type")

    for key, value in update_data.items():
        setattr(doc_type, key, value)
    await db.commit()
    await db.refresh(doc_type)
    return doc_type


async def delete_document_type(db: AsyncSession, type_id: str) -> bool:
    doc_type = await get_document_type(db, type_id)
    if not doc_type:
        return False
    doc_type.is_deleted = True
    await db.commit()
    return True


async def bulk_delete_document_types(db: AsyncSession, project_id: str, ids: list[str]) -> int:
    result = await db.execute(
        update(DocumentType)
        .where(
            DocumentType.project_id == project_id,
            DocumentType.id.in_(ids),
            DocumentType.is_deleted == False,
        )
        .values(is_deleted=True)
    )
    await db.commit()
    return result.rowcount

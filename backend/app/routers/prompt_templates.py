from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_active_user
from app.auth.permissions import RequireProjectPermission
from app.database import get_db
from app.models.prompt_template import PromptTemplate
from app.services.llm.prompt_templates import get_builtin_template, list_builtin_templates

router = APIRouter(tags=["Prompt Templates"])

PROMPT_KEYS = ("system", "extraction", "classification")


class PromptTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    prompts: dict[str, str] = {}
    is_shared: bool = False


class PromptTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompts: dict[str, str] | None = None
    is_shared: bool | None = None


class PromptTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    name: str
    description: str | None = None
    prompts: dict = {}
    is_shared: bool = False
    builtin: bool = False


def _clean_prompts(prompts: dict) -> dict:
    cleaned = {}
    for key in PROMPT_KEYS:
        val = (prompts or {}).get(key)
        if isinstance(val, str) and val.strip():
            cleaned[key] = val
    if not cleaned:
        raise HTTPException(status_code=400, detail="At least one prompt (system/extraction/classification) is required")
    return cleaned


@router.get("/api/v1/prompt-templates/built-in")
async def list_builtin(user=Depends(get_current_active_user)):
    return [{**t, "builtin": True, "project_id": None} for t in list_builtin_templates()]


@router.get("/api/v1/projects/{project_id}/prompt-templates", response_model=list[PromptTemplateResponse])
async def list_templates(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:read")),
):
    result = await db.execute(
        select(PromptTemplate)
        .where(
            or_(
                PromptTemplate.project_id == project_id,
                PromptTemplate.is_shared == True,  # noqa: E712
            )
        )
        .order_by(PromptTemplate.name)
    )
    return [PromptTemplateResponse.model_validate(t, from_attributes=True) for t in result.scalars().all()]


@router.post("/api/v1/projects/{project_id}/prompt-templates", response_model=PromptTemplateResponse, status_code=201)
async def create_template(
    project_id: str,
    data: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    from app.services.project_service import get_project

    if not await get_project(db, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    template = PromptTemplate(
        project_id=project_id,
        name=data.name.strip(),
        description=(data.description or "").strip() or None,
        prompts=_clean_prompts(data.prompts),
        is_shared=bool(data.is_shared),
        created_by=user.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return PromptTemplateResponse.model_validate(template, from_attributes=True)


async def _get_owned(db: AsyncSession, project_id: str, template_id: str) -> PromptTemplate:
    template = await db.get(PromptTemplate, template_id)
    if not template or template.project_id != project_id:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.patch("/api/v1/projects/{project_id}/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
async def update_template(
    project_id: str,
    template_id: str,
    data: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    template = await _get_owned(db, project_id, template_id)
    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(status_code=400, detail="Name is required")
        template.name = data.name.strip()
    if data.description is not None:
        template.description = data.description.strip() or None
    if data.prompts is not None:
        template.prompts = _clean_prompts(data.prompts)
    if data.is_shared is not None:
        template.is_shared = bool(data.is_shared)
    await db.commit()
    await db.refresh(template)
    return PromptTemplateResponse.model_validate(template, from_attributes=True)


@router.delete("/api/v1/projects/{project_id}/prompt-templates/{template_id}", status_code=204)
async def delete_template(
    project_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    template = await _get_owned(db, project_id, template_id)
    await db.delete(template)
    await db.commit()
    return None


@router.get("/api/v1/projects/{project_id}/prompt-templates/{template_id}", response_model=PromptTemplateResponse)
async def get_template(
    project_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:read")),
):
    if template_id.startswith("builtin:"):
        builtin = get_builtin_template(template_id)
        if not builtin:
            raise HTTPException(status_code=404, detail="Template not found")
        return {**builtin, "builtin": True, "project_id": project_id}
    template = await db.get(PromptTemplate, template_id)
    if not template or (template.project_id != project_id and not template.is_shared):
        raise HTTPException(status_code=404, detail="Template not found")
    return PromptTemplateResponse.model_validate(template, from_attributes=True)

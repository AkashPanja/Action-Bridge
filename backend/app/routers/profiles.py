import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import RequireProjectPermission
from app.database import get_db
from app.models.document_type import DocumentType
from app.models.extraction_profile import DEFAULT_PROMPTS, PROFILE_MODES, ExtractionProfile
from app.models.llm_provider import LlmProvider
from app.schemas.extraction import (
    PlaygroundResponse,
    ProfileCreate,
    ProfileResponse,
    ProfileUpdate,
)
from app.services import extraction, ingestion

router = APIRouter(prefix="/api/v1/projects/{project_id}/profiles", tags=["Profiles"])


async def _get_profile(db: AsyncSession, project_id: str, profile_id: str) -> ExtractionProfile:
    profile = await db.get(ExtractionProfile, profile_id)
    if not profile or profile.project_id != project_id:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


async def _validate_refs(db: AsyncSession, project_id: str, data: dict):
    mode = data.get("mode")
    if mode is not None and mode not in PROFILE_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {PROFILE_MODES}")
    for cand in data.get("candidate_types") or []:
        tid = cand.get("document_type_id") if isinstance(cand, dict) else getattr(cand, "document_type_id", None)
        if not tid:
            raise HTTPException(status_code=400, detail="candidate_types entries need document_type_id")
        dtype = await db.get(DocumentType, tid)
        if not dtype or dtype.project_id != project_id:
            raise HTTPException(status_code=400, detail="Candidate type not in this project")
    target = data.get("target_document_type_id")
    if target:
        dtype = await db.get(DocumentType, target)
        if not dtype or dtype.project_id != project_id:
            raise HTTPException(status_code=400, detail="Target type not in this project")
    for pid in data.get("provider_chain") or []:
        provider = await db.get(LlmProvider, pid)
        if not provider:
            raise HTTPException(status_code=400, detail=f"Provider not found: {pid}")
    ocr_id = data.get("ocr_provider_id")
    if ocr_id:
        ocr = await db.get(LlmProvider, ocr_id)
        if not ocr:
            raise HTTPException(status_code=400, detail="OCR provider not found")
        if not ocr.vision:
            raise HTTPException(status_code=400, detail="OCR provider is not vision-capable")


def _merged_prompts(data) -> dict:
    merged = dict(DEFAULT_PROMPTS)
    if data and data.prompts:
        for key in ("system", "extraction", "classification"):
            val = getattr(data.prompts, key, None)
            if val:
                merged[key] = val
    return merged


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:read")),
):
    result = await db.execute(
        select(ExtractionProfile).where(ExtractionProfile.project_id == project_id)
        .order_by(ExtractionProfile.name)
    )
    return result.scalars().all()


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(
    project_id: str,
    data: ProfileCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    payload = data.model_dump()
    await _validate_refs(db, project_id, payload)
    profile = ExtractionProfile(
        project_id=project_id,
        name=data.name,
        mode=data.mode,
        candidate_types=[c.model_dump() for c in data.candidate_types],
        target_document_type_id=data.target_document_type_id,
        prompts=_merged_prompts(data),
        provider_chain=data.provider_chain,
        ocr_provider_id=data.ocr_provider_id,
        allow_cloud=data.allow_cloud,
        version=1,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    project_id: str,
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:read")),
):
    return await _get_profile(db, project_id, profile_id)


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    project_id: str,
    profile_id: str,
    data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    profile = await _get_profile(db, project_id, profile_id)
    payload = data.model_dump(exclude_unset=True)
    await _validate_refs(db, project_id, payload)
    changed_prompts = False
    if "name" in payload and payload["name"]:
        profile.name = payload["name"]
    if "mode" in payload and payload["mode"]:
        profile.mode = payload["mode"]
    if "candidate_types" in payload and payload["candidate_types"] is not None:
        profile.candidate_types = [c.model_dump() if hasattr(c, "model_dump") else c
                                   for c in payload["candidate_types"]]
    if "target_document_type_id" in payload:
        profile.target_document_type_id = payload["target_document_type_id"]
    if data.prompts:
        merged = dict(profile.prompts or {})
        for key in ("system", "extraction", "classification"):
            val = getattr(data.prompts, key, None)
            if val:
                merged[key] = val
                changed_prompts = True
        profile.prompts = merged
    if "provider_chain" in payload and payload["provider_chain"] is not None:
        profile.provider_chain = payload["provider_chain"]
    if "ocr_provider_id" in payload:
        profile.ocr_provider_id = payload["ocr_provider_id"]
    if "allow_cloud" in payload and payload["allow_cloud"] is not None:
        profile.allow_cloud = payload["allow_cloud"]
    if changed_prompts:
        profile.version = (profile.version or 1) + 1
    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    project_id: str,
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    profile = await _get_profile(db, project_id, profile_id)
    await db.delete(profile)
    await db.commit()
    return None


@router.post("/{profile_id}/playground", response_model=PlaygroundResponse)
async def playground(
    project_id: str,
    profile_id: str,
    text: str | None = Form(default=None),
    document_type_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("document_types:write")),
):
    """Test run with current prompts. Creates nothing (FR-4.5)."""
    profile = await _get_profile(db, project_id, profile_id)
    content = text or ""
    filename = "pasted-text.txt"
    if file is not None:
        raw = await file.read()
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Playground file must be under 5 MB")
        filename = file.filename or filename
        record = ingestion.store_upload(filename, raw, f"playground-{profile.id}")
        content, source, _ = ingestion.acquire_text(record["storage_path"], record["mime"])
        if not content:
            return PlaygroundResponse(errors=[f"no extractable text ({source})"])
    if not content.strip():
        raise HTTPException(status_code=400, detail="Provide text or a file")

    started = time.perf_counter()
    try:
        candidates = profile.candidate_types or []
        usable = [c for c in candidates if not c.get("ignore")]
        target_id = document_type_id
        classification = None
        if not target_id:
            if len(usable) == 1:
                target_id = usable[0].get("document_type_id")
            elif usable:
                providers = await extraction.resolve_chain(db, profile)
                target_id, meta = await extraction.classify(
                    db, profile, providers, filename, "", content[:4000], usable)
                classification = meta.get("raw_answer")
        if not target_id:
            return PlaygroundResponse(errors=["unclassified (other)"],
                                       latency_ms=int((time.perf_counter() - started) * 1000))
        doc_type = await db.get(DocumentType, target_id)
        if not doc_type or doc_type.project_id != project_id:
            raise HTTPException(status_code=400, detail="Document type not in this project")
        result = await extraction.extract_one(db, profile, doc_type, content)
        return PlaygroundResponse(
            data=result.data, errors=[],
            classification=classification,
            provider=result.meta.get("provider"), model=result.meta.get("model"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens_in=result.meta.get("tokens_in"), tokens_out=result.meta.get("tokens_out"),
        )
    except extraction.ExtractionFailed as exc:
        return PlaygroundResponse(errors=[str(exc)],
                                   latency_ms=int((time.perf_counter() - started) * 1000))

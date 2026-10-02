"""Extraction pipeline orchestration: intake, submission processing, webhooks (M2)."""

import hashlib
import hmac
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_type import DocumentType
from app.models.extraction_profile import DEFAULT_PROMPTS, ExtractionProfile
from app.models.job import Job
from app.models.llm_provider import LlmProvider
from app.models.submission import SUBMISSION_SOURCES, Submission, SubmissionFile
from app.services import document_service, extraction, ingestion, job_service
from app.services.extraction import ExtractionFailed

WEBHOOK_TIMEOUT_S = 10
WEBHOOK_TRIES = 3


# --- Intake ---

async def _sha256_seen(db: AsyncSession, project_id: str, sha256: str) -> bool:
    result = await db.execute(
        select(SubmissionFile.id)
        .join(Submission, Submission.id == SubmissionFile.submission_id)
        .where(Submission.project_id == project_id, SubmissionFile.sha256 == sha256)
        .limit(1)
    )
    return result.first() is not None


async def intake_files(
    db: AsyncSession,
    project_id: str,
    source: str,
    files: list[tuple[str, bytes]],
    profile_id: str | None = None,
    document_type_id: str | None = None,
    idempotency_key: str | None = None,
    email_meta: dict | None = None,
    note: str | None = None,
    created_by: str | None = None,
    api_key_id: str | None = None,
    max_mb: int | None = None,
) -> Submission:
    """Store an upload batch / API call as a submission with filtered files."""
    if source not in SUBMISSION_SOURCES:
        raise ValueError(f"Unknown source: {source}")
    submission = Submission(
        project_id=project_id,
        source=source,
        profile_id=profile_id,
        email_meta=email_meta,
        created_by=created_by,
        api_key_id=api_key_id,
        idempotency_key=idempotency_key,
        note=note,
    )
    db.add(submission)
    await db.flush()

    for filename, content in files:
        record = ingestion.store_upload(filename, content, submission.id)
        accepted, reason = ingestion.filter_file(record["filename"], record["size"], max_mb)
        status, skip_reason = "pending", None
        if not accepted:
            status, skip_reason = "skipped", reason
        elif await _sha256_seen(db, project_id, record["sha256"]):
            status, skip_reason = "duplicate", "duplicate file"
        db.add(SubmissionFile(
            submission_id=submission.id,
            filename=record["filename"],
            mime=record["mime"],
            size=record["size"],
            sha256=record["sha256"],
            storage_path=record["storage_path"],
            status=status,
            skip_reason=skip_reason,
        ))
    # Stash the requested type for auto mode (not a column; carried via note-free path).
    if document_type_id and not profile_id:
        submission.note = ((submission.note or "") + f" [auto_type:{document_type_id}]").strip()
    await db.commit()
    await db.refresh(submission)
    return submission


async def find_submission_by_key(db: AsyncSession, project_id: str, key: str) -> Submission | None:
    result = await db.execute(
        select(Submission).where(
            Submission.project_id == project_id, Submission.idempotency_key == key
        ).order_by(Submission.created_at.desc()).limit(1)
    )
    return result.scalars().first()


async def find_job_for_submission(db: AsyncSession, submission_id: str) -> Job | None:
    result = await db.execute(
        select(Job).where(Job.submission_id == submission_id)
        .order_by(Job.created_at.desc()).limit(1)
    )
    return result.scalars().first()


# --- Profile resolution ---

async def _resolve_profile(
    db: AsyncSession, submission: Submission
) -> tuple[ExtractionProfile | None, DocumentType | None, list[LlmProvider]]:
    """Returns (profile or None, auto doc_type or None, candidate providers)."""
    if submission.profile_id:
        profile = await db.get(ExtractionProfile, submission.profile_id)
        return profile, None, []
    # Auto mode: document_type_id stashed in note by intake_files.
    import re

    match = re.search(r"\[auto_type:([^\]]+)\]", submission.note or "")
    if match:
        doc_type = await db.get(DocumentType, match.group(1))
        if doc_type and doc_type.project_id == submission.project_id:
            providers = (await db.execute(
                select(LlmProvider).where(LlmProvider.enabled == True)  # noqa: E712
                .order_by(LlmProvider.is_local.desc())
            )).scalars().all()
            return None, doc_type, list(providers)
    return None, None, []


def _synthetic_profile(doc_type: DocumentType, providers: list[LlmProvider]) -> ExtractionProfile:
    profile = ExtractionProfile(
        project_id=doc_type.project_id,
        name="auto",
        mode="per_attachment",
        candidate_types=[{"document_type_id": doc_type.id, "name": doc_type.name, "ignore": False}],
        target_document_type_id=doc_type.id,
        prompts=dict(DEFAULT_PROMPTS),
        provider_chain=[p.id for p in providers],
        allow_cloud=True,
        version=0,
    )
    return profile


# --- Document hand-off ---

async def _submit_extracted(
    db: AsyncSession,
    project_id: str,
    doc_type: DocumentType,
    data: dict,
    scores: dict,
    signals: dict,
    meta: dict,
    submission: Submission,
    actor: str,
) -> str:
    result = await document_service.submit_document(
        db, project_id, doc_type.id, data, scores, actor,
        force_pending_review=True,
    )
    if isinstance(result, str):
        raise ExtractionFailed(f"Review hand-off rejected: {result}", reason="handoff_rejected")
    result.submission_id = submission.id
    result.source = submission.source
    result.extraction_meta = {
        "signals": signals,
        "provider": meta.get("provider"),
        "model": meta.get("model"),
        "prompt_version": meta.get("prompt_version"),
        "tokens_in": meta.get("tokens_in"),
        "tokens_out": meta.get("tokens_out"),
        "latency_ms": meta.get("latency_ms"),
        "retries": meta.get("retries", 0),
    }
    await db.commit()
    await db.refresh(result)
    return result.id


async def _manual_entry_doc(
    db: AsyncSession, project_id: str, doc_type: DocumentType,
    submission: Submission, reason: str, actor: str,
) -> str:
    """Scanned/unreadable file goes to review empty for human entry (spec 5.7.2)."""
    return await _submit_extracted(
        db, project_id, doc_type, {}, {},
        {"status": "extraction_failed", "reason": reason},
        {"provider": None, "model": None, "prompt_version": None}, submission, actor,
    )


async def _file_text(
    db: AsyncSession, sfile: SubmissionFile, profile: ExtractionProfile, job_id: str | None
) -> tuple[str, dict]:
    """Returns (text, ocr_meta). May raise ExtractionFailed -> manual entry."""
    text, source, text_path = ingestion.acquire_text(sfile.storage_path, sfile.mime)
    sfile.text_path = text_path
    sfile.text_source = source
    if text:
        return text, {}
    if source != "scanned":
        raise ExtractionFailed(f"Unreadable file ({source}).", reason="unreadable")
    # Scanned: route through the vision OCR provider.
    ocr = await db.get(LlmProvider, profile.ocr_provider_id) if profile.ocr_provider_id else None
    if not ocr or not ocr.vision:
        raise ExtractionFailed("needs manual entry", reason="needs_manual_entry")
    if not profile.allow_cloud and not ocr.is_local:
        raise ExtractionFailed("needs manual entry", reason="needs_manual_entry")
    transcribed, ocr_meta = await extraction.ocr_transcribe(
        db, ocr, sfile.storage_path, sfile.mime, job_id=job_id
    )
    sfile.text_source = "ocr"
    return transcribed, ocr_meta


# --- Submission processing ---

async def process_submission(db: AsyncSession, submission_id: str, job_id: str | None = None) -> dict:
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise ExtractionFailed("Submission not found.", reason="no_submission")

    profile, auto_type, auto_providers = await _resolve_profile(db, submission)
    if profile is None and auto_type is None:
        raise ExtractionFailed("No extraction profile or document type.", reason="no_profile")
    active = profile or _synthetic_profile(auto_type, auto_providers)
    actor = "extractor"

    files = (await db.execute(
        select(SubmissionFile).where(SubmissionFile.submission_id == submission.id)
        .order_by(SubmissionFile.created_at.asc())
    )).scalars().all()
    pending = [f for f in files if f.status == "pending"]
    document_ids: list[str] = []

    if active.mode == "combined":
        document_ids = await _process_combined(db, submission, active, pending, actor, job_id)
    else:
        for sfile in pending:
            try:
                doc_id = await _process_one_file(db, submission, active, sfile, actor, job_id)
                if doc_id:
                    document_ids.append(doc_id)
            except ExtractionFailed as exc:
                sfile.status = "failed"
                sfile.skip_reason = f"{exc.reason}: {exc}"[:255]
        await db.commit()
    return {"submission_id": submission.id, "document_ids": document_ids}


async def _process_one_file(
    db: AsyncSession, submission: Submission, profile: ExtractionProfile,
    sfile: SubmissionFile, actor: str, job_id: str | None,
) -> str | None:
    sfile.status = "processing"
    candidates = [c for c in (profile.candidate_types or []) if isinstance(c, dict)]
    usable = [c for c in candidates if not c.get("ignore")]
    if not usable:
        sfile.status = "skipped"
        sfile.skip_reason = "no candidate types"
        return None

    try:
        text, _ = await _file_text(db, sfile, profile, job_id)
    except ExtractionFailed as exc:
        if exc.reason in ("needs_manual_entry",):
            target = await _target_type(db, profile, usable[0].get("document_type_id"))
            if target:
                doc_id = await _manual_entry_doc(
                    db, submission.project_id, target, submission, exc.reason, actor)
                sfile.status = "extracted"
                sfile.document_id = doc_id
                sfile.detected_type = target.id
                await db.commit()
                return doc_id
        raise

    if len(usable) == 1:
        type_id = usable[0].get("document_type_id")
        classify_meta = {"skipped": "single candidate"}
    else:
        providers = await extraction.resolve_chain(db, profile)
        type_id, classify_meta = await extraction.classify(
            db, profile, providers, sfile.filename,
            (submission.email_meta or {}).get("subject", "") if submission.email_meta else "",
            text, usable, job_id,
        )
        _ = classify_meta
    if not type_id:
        sfile.status = "skipped"
        sfile.skip_reason = "unclassified (other)"
        await db.commit()
        return None

    doc_type = await db.get(DocumentType, type_id)
    if not doc_type or doc_type.project_id != submission.project_id:
        sfile.status = "failed"
        sfile.skip_reason = "candidate type not in project"
        await db.commit()
        return None

    result = await extraction.extract_one(db, profile, doc_type, text, job_id)
    doc_id = await _submit_extracted(
        db, submission.project_id, doc_type, result.data, result.scores,
        result.signals, result.meta, submission, actor,
    )
    sfile.status = "extracted"
    sfile.document_id = doc_id
    sfile.detected_type = doc_type.id
    await db.commit()
    return doc_id


async def _target_type(db: AsyncSession, profile: ExtractionProfile, fallback_id: str | None):
    tid = profile.target_document_type_id or fallback_id
    if not tid:
        return None
    return await db.get(DocumentType, tid)


async def _process_combined(
    db: AsyncSession, submission: Submission, profile: ExtractionProfile,
    files: list[SubmissionFile], actor: str, job_id: str | None,
) -> list[str]:
    target = await _target_type(db, profile, None)
    if not target:
        for sfile in files:
            sfile.status = "failed"
            sfile.skip_reason = "combined mode needs target_document_type"
        await db.commit()
        return []

    parts: list[str] = []
    usable_files: list[SubmissionFile] = []
    for i, sfile in enumerate(files, 1):
        sfile.status = "processing"
        try:
            text, _ = await _file_text(db, sfile, profile, job_id)
        except ExtractionFailed as exc:
            if exc.reason in ("needs_manual_entry",):
                parts.append(f"=== FILE {i}: {sfile.filename} ===\n[UNREADABLE: needs manual entry]")
                usable_files.append(sfile)
                continue
            sfile.status = "failed"
            sfile.skip_reason = f"{exc.reason}: {exc}"[:255]
            continue
        parts.append(f"=== FILE {i}: {sfile.filename} ===\n{text}")
        usable_files.append(sfile)
    if not parts:
        await db.commit()
        return []

    result = await extraction.extract_one(db, profile, target, "\n\n".join(parts), job_id)
    doc_id = await _submit_extracted(
        db, submission.project_id, target, result.data, result.scores,
        result.signals, result.meta, submission, actor,
    )
    for sfile in usable_files:
        sfile.status = "extracted"
        sfile.document_id = doc_id
    await db.commit()
    return [doc_id]


# --- Job handlers ---

async def _extract_handler(db: AsyncSession, job: Job):
    submission_id = (job.payload or {}).get("submission_id")
    if not submission_id:
        raise ExtractionFailed("Extract job missing submission_id.", reason="bad_payload")
    outcome = await process_submission(db, submission_id, job.id)
    callback_url = (job.payload or {}).get("callback_url")
    if callback_url:
        project_id = (await db.get(Job, job.id)).project_id or ""
        body = {"job_id": job.id, "status": "succeeded", **outcome,
                "review_urls": [f"/projects/{project_id}/documents/{d}"
                                for d in outcome["document_ids"]]}
        await job_service.enqueue(db, "webhook", {"url": callback_url, "body": body},
                                  project_id=job.project_id, max_attempts=5)
    return outcome, {}


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def send_webhook(url: str, body: dict, secret: str) -> None:
    import json

    raw = json.dumps(body).encode()
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_S) as client:
            resp = await client.post(url, content=raw,
                                     headers={"Content-Type": "application/json",
                                              "X-ActionBridge-Signature": _sign(secret, raw)})
    except httpx.HTTPError as exc:
        raise RuntimeError(f"webhook delivery failed: {exc}") from exc
    if resp.status_code >= 500 or resp.status_code == 429:
        raise RuntimeError(f"webhook returned {resp.status_code}")
    if resp.status_code >= 400:
        from app.services.llm.base import ProviderError

        raise ProviderError(f"webhook rejected with {resp.status_code} (no retry)", transient=False)


async def _webhook_handler(db: AsyncSession, job: Job):
    from app.config import settings

    url = (job.payload or {}).get("url")
    body = (job.payload or {}).get("body", {})
    if not url:
        raise ExtractionFailed("Webhook job missing url.", reason="bad_payload")
    if ingestion.is_private_url(url):
        raise ExtractionFailed("Webhook URL is private.", reason="bad_url")
    await send_webhook(url, body, settings.app_encryption_key or settings.secret_key)
    return {"delivered": True}, {}


job_service.register_kind("extract", _extract_handler)
job_service.register_kind("webhook", _webhook_handler)

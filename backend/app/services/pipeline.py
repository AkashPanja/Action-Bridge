"""Extraction pipeline orchestration: intake, submission processing, webhooks (M2)."""

import asyncio
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


# --- Intake ---

async def _find_duplicate_doc(db: AsyncSession, project_id: str, sha256: str) -> str | None:
    """Latest live document already produced from this file hash in this project."""
    from app.models.document_instance import DocumentInstance

    result = await db.execute(
        select(SubmissionFile.document_id)
        .join(Submission, Submission.id == SubmissionFile.submission_id)
        .join(DocumentInstance, DocumentInstance.id == SubmissionFile.document_id)
        .where(
            Submission.project_id == project_id,
            SubmissionFile.sha256 == sha256,
            SubmissionFile.document_id.is_not(None),
            DocumentInstance.is_deleted == False,
        )
        .order_by(SubmissionFile.created_at.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _find_inflight_duplicate(db: AsyncSession, project_id: str, sha256: str) -> bool:
    """Same hash already queued or processing in this project (no document yet)."""
    result = await db.execute(
        select(SubmissionFile.id)
        .join(Submission, Submission.id == SubmissionFile.submission_id)
        .where(
            Submission.project_id == project_id,
            SubmissionFile.sha256 == sha256,
            SubmissionFile.status.in_(["pending", "processing"]),
        )
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

    stored_paths: list[str] = []
    try:
        for filename, content in files:
            record = ingestion.store_upload(filename, content, submission.id)
            stored_paths.append(record["storage_path"])
            accepted, reason = ingestion.filter_file(record["filename"], record["size"], max_mb)
            status, skip_reason, linked_doc = "pending", None, None
            if not accepted:
                status, skip_reason = "skipped", reason
        else:
            linked_doc = await _find_duplicate_doc(db, project_id, record["sha256"])
            if linked_doc:
                status = "duplicate"
                skip_reason = "duplicate file — already processed, see linked document"
            elif await _find_inflight_duplicate(db, project_id, record["sha256"]):
                # Same bytes already queued/processing (e.g. double-clicked upload):
                # don't extract twice; the first run's document will serve both.
                status = "duplicate"
                skip_reason = "duplicate file — same file already being processed"
            db.add(SubmissionFile(
                submission_id=submission.id,
                filename=record["filename"],
                mime=record["mime"],
                size=record["size"],
                sha256=record["sha256"],
                storage_path=record["storage_path"],
                status=status,
                skip_reason=skip_reason,
                document_id=linked_doc,
            ))
    except Exception:
        # R14: intake holds no DB rows yet (single commit below), but files are
        # already on disk — remove them so a failed intake leaves no orphans.
        import os as _os

        for path in stored_paths:
            try:
                _os.remove(path)
            except OSError:
                pass
        raise
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

def _min_score(scores: dict) -> float | None:
    """Lowest numeric score across fields and table cells (None when empty).

    Bookkeeping keys (overall_confidence, warnings) are metadata about the
    extraction, not document facts — grounding them is meaningless, so they
    don't count toward the auto-approve decision (their scores are still
    stored for display).
    """
    ignored = {"overall_confidence", "warnings"}
    flat: list[float] = []
    for key, value in (scores or {}).items():
        if key in ignored:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            flat.append(float(value))
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, dict):
                    flat.extend(float(v) for v in row.values()
                                if isinstance(v, (int, float)) and not isinstance(v, bool))
    return min(flat) if flat else None


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
    from app.services import processing_service

    settings = await processing_service.get_settings(db)
    try:
        threshold = float(settings.get("auto_approve_threshold", 0.92))
    except (TypeError, ValueError):
        threshold = 0.92
    lowest = _min_score(scores)
    # FR-8.1b: high-confidence extractions skip forced review. Empty scores
    # (manual entry), failing threshold, or validation issues still route to humans.
    force_review = lowest is None or threshold <= 0 or lowest < threshold
    result = await document_service.submit_document(
        db, project_id, doc_type.id, data, scores, actor,
        force_pending_review=force_review,
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
        "min_score": lowest,
        "auto_approve_threshold": threshold,
        "auto_approved": result.status == "approved",
    }
    if meta.get("warnings"):
        result.extraction_meta["warnings"] = meta["warnings"]
    # Prefer the model's self-assessed overall score when it reports one.
    if meta.get("overall_confidence") is not None:
        result.confidence_score = meta["overall_confidence"]
        result.extraction_meta["overall_confidence"] = meta["overall_confidence"]
    await db.commit()
    await db.refresh(result)
    # Surface schema/validation-rule violations from the hand-off as warnings
    # so reviewers see pattern failures next to the fields.
    issues = await _handoff_issues(db, result.id)
    if issues:
        result.extraction_meta = {**(result.extraction_meta or {}), "validation_issues": issues}
        await db.commit()
        await db.refresh(result)
    return result.id


async def _handoff_issues(db: AsyncSession, document_id: str) -> list[str]:
    """Parse the hand-off audit comment for validation issues (read-only)."""
    from sqlalchemy import select as _select

    from app.models.audit_event import AuditEvent

    events = (await db.execute(
        _select(AuditEvent)
        .where(AuditEvent.document_id == document_id, AuditEvent.action == "STATUS_CHANGED")
        .order_by(AuditEvent.timestamp.desc())
        .limit(1)
    )).scalars().all()
    if not events:
        return []
    comment = events[0].comment or ""
    prefix = "Validation issues: "
    if not comment.startswith(prefix):
        return []
    return [issue.strip() for issue in comment[len(prefix):].split(";") if issue.strip()]


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
    # R17: retries must re-attempt failed files, otherwise a retried job finds
    # nothing pending and "succeeds" empty. Permanent failures simply fail again
    # (bounded by max_attempts); skips/duplicates are never touched.
    # "processing" files are always safe to reset: they prove no worker holds
    # them (a new run only starts after claim), covering crashes and
    # non-ExtractionFailed exits that bypass per-file status updates.
    reset_statuses = {"processing"}
    if job_id:
        job = await db.get(Job, job_id)
        if job and job.attempts > 0:
            reset_statuses.add("failed")
    reset = 0
    for f in files:
        if f.status in reset_statuses:
            f.status = "pending"
            f.skip_reason = None
            reset += 1
    if reset:
        await db.commit()
    pending = [f for f in files if f.status == "pending"]
    document_ids: list[str] = []

    if active.mode == "combined":
        try:
            document_ids = await _process_combined(db, submission, active, pending, actor, job_id)
        except ExtractionFailed as exc:
            # R5: files that went into the failed extraction must not stay
            # "processing" forever — mark them failed with the reason.
            for sfile in pending:
                if sfile.status == "processing":
                    sfile.status = "failed"
                    sfile.skip_reason = f"{exc.reason}: {exc}"[:255]
            await db.commit()
            raise
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
    existing_docs = [f.document_id for f in files if f.document_id]
    if not document_ids and not existing_docs:
        failed = [f for f in files if f.status == "failed"]
        if failed:
            reasons = "; ".join(f"{f.filename}: {f.skip_reason}" for f in failed)[:500]
            raise ExtractionFailed(
                f"No documents produced. {len(failed)} file(s) failed: {reasons}",
                reason="all_files_failed",
            )
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
        text, ocr_meta = await _file_text(db, sfile, profile, job_id)
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
    if ocr_meta:
        result.meta["ocr"] = ocr_meta
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
    ocr_metas: list[dict] = []
    for i, sfile in enumerate(files, 1):
        sfile.status = "processing"
        try:
            text, file_ocr = await _file_text(db, sfile, profile, job_id)
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
        if file_ocr:
            ocr_metas.append({"file": sfile.filename, **file_ocr})
    if not parts:
        await db.commit()
        return []

    result = await extraction.extract_one(db, profile, target, "\n\n".join(parts), job_id)
    if ocr_metas:
        result.meta["ocr_files"] = ocr_metas
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

# Spec section 10: one local GPU job at a time. Extract jobs serialize here
# (in addition to per-provider THROTTLES in extraction.py) because concurrent
# extractions wedge on single-GPU/HDD boxes: SQLite writer contention plus
# Ollama request pileup stalls every in-flight job with no error surfacing.
# Cloud-scale parallelism needs DB advisory locks instead (hardening).
_EXTRACT_SEMAPHORE: asyncio.Semaphore | None = None


def _extract_gate() -> asyncio.Semaphore:
    global _EXTRACT_SEMAPHORE
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _EXTRACT_SEMAPHORE is None or getattr(_EXTRACT_SEMAPHORE, "_loop", None) is not loop:
        _EXTRACT_SEMAPHORE = asyncio.Semaphore(1)
    return _EXTRACT_SEMAPHORE


async def _extract_handler(db: AsyncSession, job: Job):
    submission_id = (job.payload or {}).get("submission_id")
    if not submission_id:
        raise ExtractionFailed("Extract job missing submission_id.", reason="bad_payload")
    async with _extract_gate():
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
    secret = settings.app_encryption_key or settings.secret_key
    if not secret or secret == "change-me-in-production-use-a-long-random-string":
        raise ExtractionFailed(
            "Webhook signing secret is not configured (set APP_ENCRYPTION_KEY or SECRET_KEY).",
            reason="no_signing_secret",
        )
    await send_webhook(url, body, secret)
    return {"delivered": True}, {}


job_service.register_kind("extract", _extract_handler)
job_service.register_kind("webhook", _webhook_handler)

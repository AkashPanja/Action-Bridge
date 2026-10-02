"""LLM extraction: classification, schema-bound extraction, grounding (spec 5.7)."""

import json
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_type import DocumentType
from app.models.extraction_profile import DEFAULT_PROMPTS, ExtractionProfile
from app.models.llm_provider import LlmProvider
from app.services import ingestion
from app.services.llm.base import LlmRequest, ProviderError
from app.services.llm.factory import build_adapter
from app.services.provider_service import log_call
from app.utils.json_schema import validate_data_against_schema

ASSUMED_WINDOW = 8192
OUTPUT_RESERVE = 2048

DEFAULT_SIGNAL_MAP = {"found": 0.95, "not_found": 0.4, "retry_penalty": 0.15}


class ExtractionFailed(RuntimeError):
    """Extraction/data failures are terminal (FR-9.3: retry is for transient infra errors)."""

    def __init__(self, message: str, reason: str = "extraction_failed"):
        super().__init__(message)
        self.reason = reason
        self.transient = False


@dataclass
class ExtractResult:
    data: dict
    scores: dict
    signals: dict
    meta: dict = field(default_factory=dict)


def parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Top-level JSON must be an object")
    return parsed


def _prompts(profile: ExtractionProfile) -> dict:
    merged = dict(DEFAULT_PROMPTS)
    merged.update(profile.prompts or {})
    return merged


async def resolve_chain(db: AsyncSession, profile: ExtractionProfile) -> list[LlmProvider]:
    """Ordered, enabled providers for the profile with FR-S1 cloud gating."""
    chain: list[LlmProvider] = []
    for pid in profile.provider_chain or []:
        provider = await db.get(LlmProvider, pid)
        if provider and provider.enabled:
            chain.append(provider)
    if not profile.allow_cloud:
        chain = [p for p in chain if p.is_local]
    return chain


def _fits(provider: LlmProvider, input_tokens: int) -> bool:
    window = provider.context_window or ASSUMED_WINDOW
    return input_tokens + OUTPUT_RESERVE <= window


async def classify(
    db: AsyncSession,
    profile: ExtractionProfile,
    providers: list[LlmProvider],
    filename: str,
    subject: str,
    text: str,
    candidates: list[dict],
    job_id: str | None = None,
) -> tuple[str | None, dict]:
    """Constrained classification. Returns (document_type_id | None, meta).

    None means `other`/ignore — the caller marks the file skipped.
    """
    names = [c["name"] for c in candidates]
    by_name = {c["name"]: c["document_type_id"] for c in candidates}
    allowed = names + ["other"]
    excerpt = text[:4000]
    last_error = "no usable provider"
    for provider in providers:
        if provider.context_window and ingestion.estimate_tokens(excerpt) > provider.context_window:
            last_error = f"input_too_long for {provider.name}"
            continue
        prompt = _prompts(profile)["classification"].format(
            candidates=", ".join(f'"{n}"' for n in allowed),
            filename=filename,
            subject=subject or "-",
            text=excerpt,
        )
        adapter = await build_adapter(db, provider)
        started = time.perf_counter()
        try:
            result = await adapter.complete(LlmRequest(
                messages=[
                    {"role": "system", "content": _prompts(profile)["system"]},
                    {"role": "user", "content": prompt},
                ],
                timeout_s=provider.timeout_s,
            ))
            latency = int((time.perf_counter() - started) * 1000)
            await log_call(db, provider, True, latency, result.tokens_in, result.tokens_out, job_id=job_id)
        except ProviderError as exc:
            latency = int((time.perf_counter() - started) * 1000)
            await log_call(db, provider, False, latency, None, None, str(exc), job_id=job_id)
            last_error = str(exc)
            continue
        answer = result.text.strip().strip('"').lower()
        for name in allowed:
            if answer == name.lower():
                meta = {"provider": provider.name, "model": provider.model,
                        "latency_ms": latency, "raw_answer": result.text.strip()}
                if name == "other":
                    return None, meta
                return by_name[name], meta
        last_error = f"unparseable classification: {result.text.strip()[:100]}"
    raise ExtractionFailed(f"Classification failed: {last_error}", reason="classification_failed")


async def extract_one(
    db: AsyncSession,
    profile: ExtractionProfile,
    doc_type: DocumentType,
    text: str,
    job_id: str | None = None,
) -> ExtractResult:
    """Schema-bound extraction across the provider chain with retry (FR-5.4)."""
    providers = await resolve_chain(db, profile)
    if not providers:
        raise ExtractionFailed("No usable provider (check chain and allow_cloud).", reason="no_provider")

    prompts = _prompts(profile)
    schema = doc_type.schema_definition or {}
    schema_tokens = ingestion.estimate_tokens(json.dumps(schema))
    system_tokens = ingestion.estimate_tokens(prompts["system"])
    text_tokens = ingestion.estimate_tokens(text)
    retries = 0
    last_error = "no provider attempted"

    for provider in providers:
        if not _fits(provider, system_tokens + schema_tokens + text_tokens):
            last_error = f"input_too_long for {provider.name}"
            continue
        adapter = await build_adapter(db, provider)
        body = prompts["extraction"].replace("{text}", text)
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": body},
        ]
        use_schema = schema if (provider.json_schema or provider.json_object) else None
        for attempt in (1, 2):
            started = time.perf_counter()
            try:
                result = await adapter.complete(LlmRequest(
                    messages=list(messages), schema=use_schema, timeout_s=provider.timeout_s,
                ))
                latency = int((time.perf_counter() - started) * 1000)
            except ProviderError as exc:
                latency = int((time.perf_counter() - started) * 1000)
                await log_call(db, provider, False, latency, None, None, str(exc), job_id=job_id)
                last_error = str(exc)
                if getattr(exc, "transient", False):
                    break  # transient: next provider, not prompt retry
                last_error = f"{provider.name}: {exc}"
                break
            try:
                data = parse_json_response(result.text)
                issues = validate_data_against_schema(data, schema)
            except Exception as exc:
                issues = [f"unparseable output: {exc}"]
                data = {}
            if not issues:
                await log_call(db, provider, True, latency, result.tokens_in, result.tokens_out, job_id=job_id)
                signals = ground_signals(data, text)
                scores = map_confidence(data, signals, await _signal_map(db))
                return ExtractResult(
                    data=data, scores=scores, signals=signals,
                    meta={
                        "provider": provider.name, "model": provider.model,
                        "prompt_version": profile.version,
                        "tokens_in": result.tokens_in, "tokens_out": result.tokens_out,
                        "latency_ms": latency, "retries": retries,
                        "json_mode": result.json_mode,
                    },
                )
            await log_call(db, provider, False, latency, result.tokens_in, result.tokens_out,
                            "; ".join(issues), job_id=job_id)
            last_error = f"{provider.name}: {'; '.join(issues)}"
            if attempt == 1:
                retries += 1
                messages = messages + [{
                    "role": "user",
                    "content": "Your previous output failed validation:\n"
                               + "\n".join(f"- {i}" for i in issues)
                               + "\nReturn corrected JSON only.",
                }]
    raise ExtractionFailed(f"Extraction failed: {last_error}", reason="validation_failed")


async def _signal_map(db: AsyncSession) -> dict:
    from app.services import processing_service

    try:
        current = await processing_service.get_settings(db)
        override = current.get("signal_confidence") or {}
    except Exception:
        override = {}
    merged = dict(DEFAULT_SIGNAL_MAP)
    merged.update({k: float(v) for k, v in override.items() if k in merged})
    return merged


def _normalize(value: object) -> str:
    s = str(value).strip().lower()
    s = " ".join(s.split())
    for ch in [",", "_", " ", "$", "€", "£", "₹"]:
        s = s.replace(ch, "")
    return s


def _value_grounded(value: object, text_norm: str, text_raw_lower: str) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return True  # presence asserted by schema; nothing textual to ground
    norm = _normalize(value)
    if not norm:
        return False
    if norm in text_norm:
        return True
    # Numeric equivalence: "1,500.00" vs "1500".
    try:
        needle = float(norm)
        import re

        for token in set(re.findall(r"[\d.,]+", text_raw_lower)):
            try:
                if float(token.replace(",", "")) == needle:
                    return True
            except ValueError:
                continue
    except ValueError:
        pass
    return str(value).strip().lower() in text_raw_lower


def _row_found(row_sig: dict) -> bool:
    if set(row_sig) == {"found", "schema_ok", "retries"}:
        return bool(row_sig.get("found"))
    return any(c.get("found", False) for c in row_sig.values())


def ground_signals(data: dict, text: str) -> dict:
    """Per-field {found, schema_ok, retries} signals (spec 5.7 step 7)."""
    text_norm = _normalize(text)
    text_raw_lower = text.lower()
    signals: dict = {}
    for key, value in (data or {}).items():
        if isinstance(value, dict):
            children = {k: {"found": _value_grounded(v, text_norm, text_raw_lower),
                            "schema_ok": True, "retries": 0}
                        for k, v in value.items()}
            signals[key] = {"children": children, "found": any(c["found"] for c in children.values()),
                            "schema_ok": True, "retries": 0}
        elif isinstance(value, list):
            rows = []
            for row in value:
                if isinstance(row, dict):
                    rows.append({k: {"found": _value_grounded(v, text_norm, text_raw_lower),
                                     "schema_ok": True, "retries": 0} for k, v in row.items()})
                else:
                    rows.append({"found": _value_grounded(row, text_norm, text_raw_lower),
                                 "schema_ok": True, "retries": 0})
            signals[key] = {"rows": rows,
                            "found": any(_row_found(r) for r in rows) if rows else False,
                            "schema_ok": True, "retries": 0}
        else:
            signals[key] = {"found": _value_grounded(value, text_norm, text_raw_lower),
                            "schema_ok": True, "retries": 0}
    return signals


def map_confidence(data: dict, signals: dict, signal_map: dict) -> dict:
    """Map grounding signals to the numeric per-field scores submit_document requires.

    Nested objects collapse to the mean of their leaf scores (R3); table arrays map
    per row/column to match the existing confidence structure.
    """
    high = signal_map.get("found", 0.95)
    low = signal_map.get("not_found", 0.4)
    penalty = signal_map.get("retry_penalty", 0.15)

    def leaf_score(found: bool, retries: int) -> float:
        base = high if found else low
        return round(max(0.0, min(1.0, base - penalty * retries)), 3)

    scores: dict = {}
    for key, value in (data or {}).items():
        sig = signals.get(key, {})
        if isinstance(value, dict):
            children = sig.get("children", {})
            child_scores = [leaf_score(children.get(k, {}).get("found", False),
                                       children.get(k, {}).get("retries", 0))
                            for k in value]
            scores[key] = round(sum(child_scores) / len(child_scores), 3) if child_scores else low
        elif isinstance(value, list):
            rows = sig.get("rows", [])
            mapped_rows = []
            for row_sig in rows:
                if isinstance(row_sig, dict) and "found" in row_sig and len(row_sig) == 3 and set(row_sig) == {"found", "schema_ok", "retries"}:
                    mapped_rows.append(leaf_score(row_sig["found"], row_sig["retries"]))
                else:
                    mapped_rows.append({k: leaf_score(v.get("found", False), v.get("retries", 0))
                                        for k, v in row_sig.items()})
            # submit_document expects list-of-dicts for table fields.
            scores[key] = [
                r if isinstance(r, dict) else {"value": r} for r in mapped_rows
            ] if mapped_rows else []
        else:
            scores[key] = leaf_score(sig.get("found", False), sig.get("retries", 0))
    return scores


async def ocr_transcribe(
    db: AsyncSession,
    provider: LlmProvider,
    storage_path: str,
    mime: str,
    max_pages: int = 10,
    job_id: str | None = None,
) -> tuple[str, dict]:
    """Transcribe scanned PDFs/images via a vision provider to Markdown."""
    if not provider.vision:
        raise ExtractionFailed(f"Provider '{provider.name}' is not vision-capable.", reason="no_vision")
    import base64
    from pathlib import Path

    import pymupdf

    images: list[str] = []
    pages_used = 0
    if mime == "application/pdf" or Path(storage_path).suffix.lower() == ".pdf":
        doc = pymupdf.open(storage_path)
        try:
            for page in doc[:max_pages]:
                pix = page.get_pixmap(dpi=150)
                images.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode())
                pages_used += 1
        finally:
            doc.close()
    else:
        raw = Path(storage_path).read_bytes()
        images.append("data:image/png;base64," + base64.b64encode(raw).decode())
        pages_used = 1

    adapter = await build_adapter(db, provider)
    started = time.perf_counter()
    try:
        result = await adapter.complete(LlmRequest(
            messages=[{"role": "user",
                       "content": "Transcribe this document page to Markdown. "
                                  "Copy all text exactly; describe tables as Markdown tables. "
                                  "No commentary, transcription only."}],
            images=images,
            timeout_s=provider.timeout_s,
        ))
        latency = int((time.perf_counter() - started) * 1000)
    except ProviderError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        await log_call(db, provider, False, latency, None, None, str(exc), job_id=job_id)
        raise ExtractionFailed(f"OCR failed: {exc}", reason="ocr_failed") from exc
    await log_call(db, provider, True, latency, result.tokens_in, result.tokens_out, job_id=job_id)
    return result.text, {"provider": provider.name, "model": provider.model,
                         "pages": pages_used, "latency_ms": latency,
                         "tokens_in": result.tokens_in, "tokens_out": result.tokens_out}

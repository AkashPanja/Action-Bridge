import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.audit_event import AuditEvent
from app.models.document_instance import DocumentInstance
from app.models.document_type import DocumentType
from app.models.regex_pattern import RegexPattern
from app.services.project_service import get_project
from app.utils.fsm import can_edit, validate_transition
from app.utils.json_schema import validate_data_against_schema


def _compile_regex(pattern: str, flags: str = "") -> re.Pattern | None:
    try:
        flag_mask = 0
        if "i" in flags: flag_mask |= re.IGNORECASE
        if "m" in flags: flag_mask |= re.MULTILINE
        if "s" in flags: flag_mask |= re.DOTALL
        return re.compile(pattern, flag_mask)
    except re.error:
        return None


def _compile_pattern_entry(
    entry: dict,
    resolved: dict[str, re.Pattern] | None,
) -> re.Pattern | None:
    pid = entry.get("id")
    if pid and resolved and pid in resolved:
        return resolved[pid]
    inline = entry.get("pattern")
    if inline:
        return _compile_regex(inline)
    return None


def _validate_field_rules(
    data: dict,
    confidence_scores: dict | None,
    schema_definition: dict,
    validation_rules: dict | None,
    resolved_patterns: dict[str, re.Pattern] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not validation_rules:
        return errors
    properties = schema_definition.get("properties", {})
    for field_key, value in data.items():
        rules = validation_rules.get(field_key)
        if not rules:
            continue
        prop = properties.get(field_key, {})
        field_type = prop.get("type", "string")

        # --- confidence_min ---
        conf_min = rules.get("confidence_min")
        if conf_min is not None and confidence_scores:
            score = confidence_scores.get(field_key)
            if field_type == "array" and isinstance(score, list):
                for ri, row_scores in enumerate(score):
                    for col_key, col_val in row_scores.items():
                        col_rules = rules.get("columns", {}).get(col_key, {})
                        col_conf_min = col_rules.get("confidence_min")
                        if col_conf_min is not None and isinstance(col_val, (int, float)) and col_val < col_conf_min:
                            errors.append(f"'{field_key}'[{ri}].{col_key}: confidence {col_val:.2f} is below minimum {col_conf_min:.2f}")
            elif isinstance(score, (int, float)) and score < conf_min:
                errors.append(f"'{field_key}': confidence {score:.2f} is below minimum {conf_min:.2f}")

        if field_type == "array":
            col_rules_map = rules.get("columns", {})
            if not isinstance(value, list):
                continue
            for ri, row in enumerate(value):
                if not isinstance(row, dict):
                    continue
                for col_key, col_val in row.items():
                    col_rules = col_rules_map.get(col_key, {})
                    col_errors = _apply_value_rules(col_key, col_val, col_rules, f"'{field_key}'[{ri}].{col_key}", resolved_patterns)
                    errors.extend(col_errors)
        else:
            field_errors = _apply_value_rules(field_key, value, rules, f"'{field_key}'", resolved_patterns)
            errors.extend(field_errors)
    return errors


def _apply_value_rules(
    field_key: str, value: object, rules: dict, path: str,
    resolved_patterns: dict[str, re.Pattern] | None = None,
) -> list[str]:
    errors: list[str] = []
    min_len = rules.get("min_length")
    max_len = rules.get("max_length")
    min_val = rules.get("min_value")
    max_val = rules.get("max_value")

    if isinstance(value, str):
        if min_len is not None and len(value) < min_len:
            errors.append(f"{path}: length {len(value)} is below minimum {min_len}")
        if max_len is not None and len(value) > max_len:
            errors.append(f"{path}: length {len(value)} exceeds maximum {max_len}")

        # Backward compat: old single pattern field
        old_pattern = rules.get("pattern")
        if old_pattern:
            compiled = _compile_regex(old_pattern)
            if compiled and not compiled.search(value):
                errors.append(f"{path}: does not match pattern {old_pattern}")

        # AND patterns — all must pass
        and_entries = rules.get("and_patterns", [])
        for entry in and_entries:
            compiled = _compile_pattern_entry(entry, resolved_patterns)
            if not compiled:
                continue
            negate = entry.get("negate", False)
            matched = bool(compiled.search(value))
            if negate:
                matched = not matched
            if not matched:
                label = f"(negated) " if negate else ""
                errors.append(f"{path}: does not match {label}pattern {compiled.pattern}")

        # OR patterns — at least one must pass
        or_entries = rules.get("or_patterns", [])
        if or_entries:
            any_passed = False
            for entry in or_entries:
                compiled = _compile_pattern_entry(entry, resolved_patterns)
                if not compiled:
                    continue
                negate = entry.get("negate", False)
                matched = bool(compiled.search(value))
                if negate:
                    matched = not matched
                if matched:
                    any_passed = True
                    break
            if not any_passed:
                errors.append(f"{path}: does not match any of the OR patterns")

    elif isinstance(value, (int, float)):
        if min_val is not None and value < min_val:
            errors.append(f"{path}: value {value} is below minimum {min_val}")
        if max_val is not None and value > max_val:
            errors.append(f"{path}: value {value} exceeds maximum {max_val}")
    return errors


async def submit_document(
    db: AsyncSession,
    project_id: str,
    document_type_id: str,
    data: dict,
    confidence_scores: dict | None = None,
    actor: str = "rpa_bot",
    force_pending_review: bool = False,
) -> DocumentInstance | str:
    project = await get_project(db, project_id)
    if not project:
        return "Project not found"

    doc_type = await db.get(DocumentType, document_type_id)
    if not doc_type or doc_type.project_id != project_id:
        return "Document type not found"

    schema_errors = validate_data_against_schema(data, doc_type.schema_definition)

    # Validate that every field in extracted_data has a confidence score
    if confidence_scores:
        for key in data:
            if key not in confidence_scores:
                return f"Missing confidence score for field: '{key}'"
            score = confidence_scores[key]
            if isinstance(data[key], list):
                # Table field — confidence_scores[key] must be list of dicts
                if not isinstance(score, list):
                    return f"Invalid confidence score for table field '{key}': expected a list"
                if len(score) != len(data[key]):
                    return f"Confidence score row count for '{key}' does not match data rows"
                for ri, row_scores in enumerate(score):
                    if not isinstance(row_scores, dict):
                        return f"Invalid confidence score for '{key}' row {ri}: expected an object"
                    for col_key in row_scores:
                        col_score = row_scores[col_key]
                        if not isinstance(col_score, (int, float)) or col_score < 0 or col_score > 1:
                            return f"Invalid confidence score for '{key}'[{ri}].{col_key}: must be between 0 and 1"
            else:
                if not isinstance(score, (int, float)) or score < 0 or score > 1:
                    return f"Invalid confidence score for '{key}': must be between 0 and 1"

    avg_score = None
    if confidence_scores and data:
        scores_flat: list[float] = []
        for key in data:
            val = confidence_scores.get(key)
            if isinstance(val, list):
                for row_scores in val:
                    scores_flat.extend(row_scores.values())
            elif isinstance(val, (int, float)):
                scores_flat.append(val)
        if scores_flat:
            avg_score = sum(scores_flat) / len(scores_flat)

    doc = DocumentInstance(
        project_id=project_id,
        document_type_id=document_type_id,
        status="received",
        extracted_data=data,
        confidence_score=avg_score,
        confidence_scores=confidence_scores,
    )
    db.add(doc)
    await db.flush()

    audit = AuditEvent(
        document_id=doc.id,
        action="DOCUMENT_CREATED",
        actor=actor,
        new_value=data,
    )
    db.add(audit)

    # Resolve named regex patterns referenced in validation rules
    resolved_map: dict[str, re.Pattern] | None = None
    if doc_type.validation_rules:
        pattern_ids = set()
        for field_rules in doc_type.validation_rules.values():
            if not isinstance(field_rules, dict):
                continue
            for group in ("and_patterns", "or_patterns"):
                for entry in field_rules.get(group, []):
                    pid = entry.get("id")
                    if pid:
                        pattern_ids.add(pid)
        if pattern_ids:
            result = await db.execute(
                select(RegexPattern).where(RegexPattern.id.in_(pattern_ids))
            )
            resolved_map = {}
            for p in result.scalars().all():
                compiled = _compile_regex(p.pattern, p.flags)
                if compiled:
                    resolved_map[p.id] = compiled

    rule_errors = _validate_field_rules(data, confidence_scores, doc_type.schema_definition, doc_type.validation_rules, resolved_map)

    all_issues = schema_errors + rule_errors

    if all_issues or force_pending_review:
        comment = "Validation issues: " + "; ".join(all_issues) if all_issues else (
            "Extractor submission requires human review (auto-approve skipped)"
        )
        doc.status = "pending_review"
        audit2 = AuditEvent(
            document_id=doc.id,
            action="STATUS_CHANGED",
            actor="system",
            field_name="status",
            old_value={"status": "received"},
            new_value={"status": "pending_review"},
            comment=comment,
        )
    else:
        doc.status = "approved"
        audit2 = AuditEvent(
            document_id=doc.id,
            action="STATUS_CHANGED",
            actor="system",
            field_name="status",
            old_value={"status": "received"},
            new_value={"status": "approved"},
            comment="Auto-approved: all validations passed",
        )
    db.add(audit2)

    await db.commit()
    await db.refresh(doc)
    return doc


async def get_document(
    db: AsyncSession, document_id: str, include_history: bool = False
) -> DocumentInstance | None:
    query = select(DocumentInstance).where(
        DocumentInstance.id == document_id,
        DocumentInstance.is_deleted == False,
    )
    if include_history:
        query = query.options(joinedload(DocumentInstance.audit_events))
    result = await db.execute(query)
    return result.unique().scalar_one_or_none()


async def list_documents(
    db: AsyncSession,
    project_id: str,
    status: str | None = None,
    document_type_id: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    limit: int | None = 200,
    offset: int = 0,
) -> list[DocumentInstance]:
    query = select(DocumentInstance).where(
        DocumentInstance.project_id == project_id,
        DocumentInstance.is_deleted == False,
    )
    if status:
        query = query.where(DocumentInstance.status == status)
    if document_type_id:
        query = query.where(DocumentInstance.document_type_id == document_type_id)
    if search:
        query = query.where(
            DocumentInstance.extracted_data.astext.ilike(f"%{search}%")
        )
    if date_from:
        query = query.where(DocumentInstance.created_at >= date_from)
    if date_to:
        query = query.where(DocumentInstance.created_at <= date_to)
    if confidence_min is not None:
        query = query.where(DocumentInstance.confidence_score >= confidence_min)
    if confidence_max is not None:
        query = query.where(DocumentInstance.confidence_score <= confidence_max)

    allowed_sorts = {"created_at": DocumentInstance.created_at, "updated_at": DocumentInstance.updated_at, "confidence_score": DocumentInstance.confidence_score}
    sort_col = allowed_sorts.get(sort_by, DocumentInstance.created_at)
    order_fn = sort_col.asc if sort_order == "asc" else sort_col.desc
    query = query.order_by(order_fn())
    if limit is not None:
        query = query.limit(max(1, min(limit, 1000))).offset(max(0, offset))
    elif offset:
        query = query.offset(max(0, offset))

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_type_names(db: AsyncSession, type_ids: list[str]) -> dict[str, str]:
    """Batch-fetch document type names (avoids N+1 in list views)."""
    ids = [t for t in dict.fromkeys(type_ids) if t]
    if not ids:
        return {}
    result = await db.execute(
        select(DocumentType.id, DocumentType.name).where(DocumentType.id.in_(ids))
    )
    return {row.id: row.name for row in result}


async def update_document(
    db: AsyncSession,
    document_id: str,
    extracted_data: dict | None = None,
    new_status: str | None = None,
    comment: str | None = None,
    actor: str = "user",
) -> DocumentInstance | str | None:
    doc = await get_document(db, document_id)
    if not doc:
        return None

    if not can_edit(doc.status) and (extracted_data is not None or new_status is not None):
        return "Document is not editable in its current state"

    if extracted_data is not None:
        doc_type = await db.get(DocumentType, doc.document_type_id)
        if doc_type:
            errors = validate_data_against_schema(extracted_data, doc_type.schema_definition)
            if errors:
                return f"Validation failed: {'; '.join(errors)}"

    old_data = dict(doc.extracted_data) if doc.extracted_data else {}

    if extracted_data is not None:
        doc.extracted_data = extracted_data

    if new_status:
        if not validate_transition(doc.status, new_status):
            return f"Cannot transition from {doc.status} to {new_status}"
        audit_status = AuditEvent(
            document_id=doc.id,
            action="STATUS_CHANGED",
            actor=actor,
            field_name="status",
            old_value={"status": doc.status},
            new_value={"status": new_status},
            comment=comment,
        )
        db.add(audit_status)
        doc.status = new_status

    if extracted_data is not None:
        changed_fields = {}
        for key in extracted_data:
            if key not in old_data or old_data[key] != extracted_data[key]:
                changed_fields[key] = {
                    "old": old_data.get(key),
                    "new": extracted_data[key],
                }
        if changed_fields:
            audit_data = AuditEvent(
                document_id=doc.id,
                action="FIELD_UPDATE",
                actor=actor,
                field_name=", ".join(changed_fields.keys()),
                old_value={k: v["old"] for k, v in changed_fields.items()},
                new_value={k: v["new"] for k, v in changed_fields.items()},
                comment=comment,
            )
            db.add(audit_data)

    await db.commit()
    await db.refresh(doc)
    return doc


async def get_document_history(
    db: AsyncSession, document_id: str
) -> list[AuditEvent]:
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.document_id == document_id)
        .order_by(AuditEvent.timestamp.asc())
    )
    return list(result.scalars().all())


async def delete_document(db: AsyncSession, project_id: str, document_id: str) -> bool:
    doc = await get_document(db, document_id)
    if not doc or doc.project_id != project_id:
        return False
    doc.is_deleted = True
    await db.commit()
    return True


async def export_documents(
    db: AsyncSession,
    project_id: str,
    fmt: str,
    status: str | None = None,
    document_type_id: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
) -> tuple[list[str], list[list[str | int | float | None]]]:
    docs = await list_documents(db, project_id, status, document_type_id, search, date_from, date_to, confidence_min, confidence_max, limit=None)

    from app.models.document_type import DocumentType
    type_names: dict[str, str] = {}
    if docs:
        type_ids = list({d.document_type_id for d in docs if d.document_type_id})
        result = await db.execute(
            select(DocumentType.id, DocumentType.name).where(DocumentType.id.in_(type_ids))
        )
        type_names = {row.id: row.name for row in result}

    all_keys: list[str] = []
    seen = set()
    for d in docs:
        for k in (d.extracted_data or {}):
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    base_cols = ["ID", "Document Type", "Status", "Confidence Score", "Created At", "Updated At"]
    headers = base_cols + all_keys

    rows: list[list[str | int | float | None]] = []
    for d in docs:
        import json
        row = [
            d.id,
            type_names.get(d.document_type_id, ""),
            d.status,
            d.confidence_score,
            d.created_at.isoformat() if d.created_at else None,
            d.updated_at.isoformat() if d.updated_at else None,
        ]
        for key in all_keys:
            val = (d.extracted_data or {}).get(key)
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            row.append(val)
        rows.append(row)
    return headers, rows


async def bulk_delete_documents(db: AsyncSession, project_id: str, ids: list[str]) -> int:
    result = await db.execute(
        update(DocumentInstance)
        .where(
            DocumentInstance.project_id == project_id,
            DocumentInstance.id.in_(ids),
            DocumentInstance.is_deleted == False,
        )
        .values(is_deleted=True)
    )
    await db.commit()
    return result.rowcount

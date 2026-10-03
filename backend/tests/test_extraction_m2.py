"""M2 extraction pipeline: intake, text, classify/extract, grounding, hand-off, /extract."""

import base64
import io

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "total_amount": {"type": "number"},
        "vendor": {"type": "string"},
    },
    "required": ["invoice_number", "total_amount"],
}

INVOICE_TEXT = "Invoice INV-001\nVendor: Acme Corp\nTotal amount: 1500\nDue soon."
INVOICE_JSON = '{"invoice_number": "INV-001", "total_amount": 1500, "vendor": "Acme Corp"}'


async def create_project(client, headers, name="ExtractProj"):
    resp = await client.post("/api/v1/projects", headers=headers, json={"name": name})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def create_doc_type(client, headers, project_id, name="Invoice", schema=None):
    resp = await client.post(
        f"/api/v1/projects/{project_id}/document-types", headers=headers,
        json={"name": name, "schema_definition": schema or INVOICE_SCHEMA},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def create_provider(client, headers, name="fake-local"):
    resp = await client.post("/api/v1/llm-providers", headers=headers, json={
        "name": name, "kind": "openai_compatible",
        "base_url": "http://localhost:11434/v1", "model": "test-model",
        "is_local": True, "json_object": True,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def create_profile(client, headers, project_id, type_id, provider_id, **overrides):
    payload = {
        "name": "inv-profile", "mode": "per_attachment",
        "candidate_types": [{"document_type_id": type_id, "name": "Invoice"}],
        "target_document_type_id": type_id,
        "provider_chain": [provider_id],
        "allow_cloud": False,
    }
    payload.update(overrides)
    resp = await client.post(f"/api/v1/projects/{project_id}/profiles", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class ScriptAdapter:
    """Canned LLM responses in sequence."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    async def complete(self, request):
        from app.services.llm.base import LlmResult

        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return LlmResult(text=text, tokens_in=10, tokens_out=5, latency_ms=3, json_mode="json_object")


def patch_adapter(monkeypatch, texts):
    import app.services.extraction as ext_mod

    adapter = ScriptAdapter(texts)

    async def fake_build(db, provider):
        return adapter

    monkeypatch.setattr(ext_mod, "build_adapter", fake_build)
    return adapter


def make_pdf(text_lines):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in text_lines:
        page.insert_text((72, y), line)
        y += 20
    # Pad so the page exceeds the scanned-text threshold.
    while y < 400:
        page.insert_text((72, y), "filler text to simulate a real document page")
        y += 20
    raw = doc.tobytes()
    doc.close()
    return raw


# --- Ingestion unit tests ---

class TestIngestion:
    async def test_pdf_text(self, tmp_path, monkeypatch):
        from app.services import ingestion

        monkeypatch.setattr(ingestion.settings, "file_store_dir", str(tmp_path))
        raw = make_pdf(["Invoice INV-001", "Total 1500"])
        rec = ingestion.store_upload("inv.pdf", raw, "sub1")
        text, source, text_path = ingestion.acquire_text(rec["storage_path"], rec["mime"])
        assert source == "pdf_text"
        assert "INV-001" in text
        assert text_path != ""

    async def test_blank_pdf_is_scanned(self, tmp_path, monkeypatch):
        from app.services import ingestion

        monkeypatch.setattr(ingestion.settings, "file_store_dir", str(tmp_path))
        import pymupdf

        doc = pymupdf.open()
        doc.new_page()
        raw = doc.tobytes()
        doc.close()
        rec = ingestion.store_upload("blank.pdf", raw, "sub1")
        text, source, _ = ingestion.acquire_text(rec["storage_path"], rec["mime"])
        assert source == "scanned"
        assert text == ""

    async def test_office_and_text(self, tmp_path, monkeypatch):
        from app.services import ingestion

        monkeypatch.setattr(ingestion.settings, "file_store_dir", str(tmp_path))
        import docx

        d = docx.Document()
        d.add_paragraph("Hello docx")
        buf = io.BytesIO()
        d.save(buf)
        rec = ingestion.store_upload("a.docx", buf.getvalue(), "sub1")
        text, source, _ = ingestion.acquire_text(rec["storage_path"], rec["mime"])
        assert source == "docx" and "Hello docx" in text

        rec = ingestion.store_upload("a.txt", b"plain text", "sub1")
        text, source, _ = ingestion.acquire_text(rec["storage_path"], rec["mime"])
        assert source == "txt" and text == "plain text"

    def test_filtering(self):
        from app.services import ingestion
        assert ingestion.filter_file("a.pdf", 100)[0] is True
        ok, reason = ingestion.filter_file("a.exe", 100)
        assert ok is False and reason.startswith("unsupported_type")
        ok, reason = ingestion.filter_file("a.pdf", 30 * 1024 * 1024)
        assert ok is False and reason.startswith("oversize")
        ok, reason = ingestion.filter_file("sig.png", 500)
        assert ok is False and reason.startswith("tiny_image")

    async def test_ssrf_guards(self):
        from app.services import ingestion

        assert ingestion.is_private_url("http://127.0.0.1/x") is True
        assert ingestion.is_private_url("http://localhost:8000/x") is True
        assert ingestion.is_private_url("ftp://example.com/x") is True
        assert ingestion.is_private_url("http://169.254.169.254/") is True

    async def test_fetch_private_rejected(self):
        from app.services import ingestion

        with pytest.raises(ValueError):
            await ingestion.fetch_url("http://127.0.0.1:9/x")

    async def test_provider_url_rule(self):
        from app.services import ingestion

        ingestion.validate_provider_url("http://localhost:11434/v1", True)
        with pytest.raises(ValueError):
            ingestion.validate_provider_url("http://localhost:11434/v1", False)


# --- Grounding unit tests ---

class TestGrounding:
    async def test_found_and_missing(self):
        from app.services.extraction import ground_signals, map_confidence

        data = {"invoice_number": "INV-001", "vendor": "Nobody"}
        signals = ground_signals(data, INVOICE_TEXT)
        assert signals["invoice_number"]["found"] is True
        assert signals["vendor"]["found"] is False
        scores = map_confidence(data, signals, {"found": 0.95, "not_found": 0.4, "retry_penalty": 0.15})
        assert scores == {"invoice_number": 0.95, "vendor": 0.4}

    async def test_nested_mean_r3(self):
        from app.services.extraction import ground_signals, map_confidence

        data = {"invoice": {"number": "INV-001", "ghost": "zzz"}}
        signals = ground_signals(data, INVOICE_TEXT)
        scores = map_confidence(data, signals, {"found": 1.0, "not_found": 0.0, "retry_penalty": 0.0})
        assert scores == {"invoice": 0.5}

    async def test_table_shape(self):
        from app.services.extraction import ground_signals, map_confidence

        data = {"lines": [{"sku": "A1", "qty": 2}]}
        signals = ground_signals(data, "sku A1 qty 2")
        scores = map_confidence(data, signals, {"found": 0.9, "not_found": 0.1, "retry_penalty": 0.0})
        assert scores == {"lines": [{"sku": 0.9, "qty": 0.9}]}


# --- Profiles API ---

class TestProfiles:
    async def test_crud(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        prof = await create_profile(client, admin_headers, pid, tid, prov)

        listed = (await client.get(f"/api/v1/projects/{pid}/profiles", headers=admin_headers)).json()
        assert any(p["id"] == prof for p in listed)

        updated = (await client.patch(
            f"/api/v1/projects/{pid}/profiles/{prof}", headers=admin_headers,
            json={"mode": "combined", "prompts": {"extraction": "custom"}})).json()
        assert updated["mode"] == "combined"
        assert updated["version"] == 2  # prompt change bumps version

        resp = await client.delete(f"/api/v1/projects/{pid}/profiles/{prof}", headers=admin_headers)
        assert resp.status_code == 204

    async def test_bad_mode(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await client.post(f"/api/v1/projects/{pid}/profiles", headers=admin_headers, json={
            "name": "x", "mode": "magic",
            "candidate_types": [{"document_type_id": tid}], "provider_chain": [],
        })
        assert resp.status_code == 400

    async def test_foreign_type_rejected(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers, name="ProjA")
        other = await create_project(client, admin_headers, name="ProjB")
        tid = await create_doc_type(client, admin_headers, other)
        resp = await client.post(f"/api/v1/projects/{pid}/profiles", headers=admin_headers, json={
            "name": "x", "candidate_types": [{"document_type_id": tid}], "provider_chain": [],
        })
        assert resp.status_code == 400

    async def test_non_vision_ocr_rejected(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        resp = await client.post(f"/api/v1/projects/{pid}/profiles", headers=admin_headers, json={
            "name": "x", "candidate_types": [{"document_type_id": tid}],
            "provider_chain": [prov], "ocr_provider_id": prov,
        })
        assert resp.status_code == 400

    async def test_playground(self, client: AsyncClient, admin_headers, monkeypatch):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        prof = await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, [INVOICE_JSON])

        resp = await client.post(
            f"/api/v1/projects/{pid}/profiles/{prof}/playground",
            headers=admin_headers, data={"text": INVOICE_TEXT},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data"]["invoice_number"] == "INV-001"
        assert body["errors"] == []

    async def test_playground_reports_errors(self, client: AsyncClient, admin_headers, monkeypatch):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        prof = await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, ['{"wrong": "shape"}'])

        resp = await client.post(
            f"/api/v1/projects/{pid}/profiles/{prof}/playground",
            headers=admin_headers, data={"text": INVOICE_TEXT},
        )
        assert resp.json()["data"] is None
        assert len(resp.json()["errors"]) > 0


# --- /extract end to end ---

def b64(raw: bytes) -> str:
    import base64

    return base64.b64encode(raw).decode()


async def run_claimed_job(job_id, db_session):
    from app.services import job_service

    claimed = await job_service.claim_next(db_session)
    assert claimed is not None and claimed.id == job_id
    await job_service.run_job(claimed.id)


class TestExtract:
    async def test_json_upload_to_pending_review(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, [INVOICE_JSON])

        resp = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "document_type_id": tid,
            "files": [{"filename": "inv.txt", "content_base64": b64(INVOICE_TEXT.encode())}],
            "idempotency_key": "key-1",
        })
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["job_id"]
        await run_claimed_job(job_id, db_session)

        docs = (await client.get(
            f"/api/v1/projects/{pid}/documents", headers=admin_headers,
            params={"status": "pending_review"},
        )).json()
        assert len(docs) == 1
        doc = docs[0]
        assert doc["extracted_data"]["invoice_number"] == "INV-001"
        assert doc["submission_id"]
        assert doc["source"] in ("upload", "api")
        assert doc["extraction_meta"]["model"] == "test-model"

    async def test_idempotent(self, client: AsyncClient, admin_headers, db_session, monkeypatch):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, [INVOICE_JSON])

        body = {
            "document_type_id": tid,
            "files": [{"filename": "inv.txt", "content_base64": b64(b"hi")}],
            "idempotency_key": "same-key",
        }
        first = (await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json=body)).json()
        await run_claimed_job(first["job_id"], db_session)
        second = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json=body)
        assert second.json()["job_id"] == first["job_id"]

        docs = (await client.get(f"/api/v1/projects/{pid}/documents", headers=admin_headers)).json()
        assert len(docs) == 1

    async def test_wait_returns_completed(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, [INVOICE_JSON])

        first = (await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "document_type_id": tid,
            "files": [{"filename": "a.txt", "content_base64": b64(b"x")}],
            "idempotency_key": "wait-key",
        })).json()
        await run_claimed_job(first["job_id"], db_session)

        again = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "document_type_id": tid,
            "files": [{"filename": "a.txt", "content_base64": b64(b"x")}],
            "idempotency_key": "wait-key", "wait_seconds": 5,
        })
        body = again.json()
        assert body["status"] == "succeeded"
        assert len(body["document_ids"]) == 1
        assert body["review_urls"][0].endswith(f"/documents/{body['document_ids'][0]}")

    async def test_api_key_submit(self, client: AsyncClient, admin_headers, db_session, monkeypatch):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, [INVOICE_JSON])

        key_resp = await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": pid, "label": "ExtractBot", "scopes": ["documents:write"],
        })
        raw_key = key_resp.json()["raw_key"]
        resp = await client.post(f"/api/v1/projects/{pid}/extract/json",
                                 headers={"X-API-Key": raw_key}, json={
                                     "document_type_id": tid,
                                     "files": [{"filename": "b.txt", "content_base64": b64(b"data")}],
                                 })
        assert resp.status_code == 201, resp.text
        await run_claimed_job(resp.json()["job_id"], db_session)
        docs = (await client.get(f"/api/v1/projects/{pid}/documents", headers=admin_headers)).json()
        assert len(docs) == 1 and docs[0]["source"] == "api"

    async def test_scanned_goes_manual_entry(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        await create_profile(client, admin_headers, pid, tid, prov)
        adapter = patch_adapter(monkeypatch, [INVOICE_JSON])

        import pymupdf

        doc = pymupdf.open()
        doc.new_page()
        raw = doc.tobytes()
        doc.close()
        resp = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "document_type_id": tid,
            "files": [{"filename": "scan.pdf", "content_base64": b64(raw)}],
        })
        await run_claimed_job(resp.json()["job_id"], db_session)
        assert adapter.calls == 0  # no vision provider -> LLM never called
        docs = (await client.get(
            f"/api/v1/projects/{pid}/documents", headers=admin_headers,
            params={"status": "pending_review"},
        )).json()
        assert len(docs) == 1
        assert docs[0]["extracted_data"] == {}
        assert docs[0]["extraction_meta"]["signals"]["reason"] == "needs_manual_entry"

    async def test_combined_mode(self, client: AsyncClient, admin_headers, db_session, monkeypatch):
        combined_schema = {
            "type": "object",
            "properties": {
                "invoice": {"type": "object"},
                "grn": {"type": "object"},
            },
        }
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, name="Pair", schema=combined_schema)
        prov = await create_provider(client, admin_headers)
        await create_profile(
            client, admin_headers, pid, tid, prov, mode="combined",
            candidate_types=[],  # combined ignores candidates
        )
        patch_adapter(monkeypatch, ['{"invoice": {"n": "INV-1"}, "grn": {"n": "GRN-9"}}'])

        resp = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "profile_id": None, "document_type_id": None,
            "files": [
                {"filename": "inv.txt", "content_base64": b64(b"invoice INV-1")},
                {"filename": "grn.txt", "content_base64": b64(b"grn GRN-9")},
            ],
        })
        # No profile/type -> 400; now use the real profile.
        assert resp.status_code == 400
        profiles = (await client.get(f"/api/v1/projects/{pid}/profiles", headers=admin_headers)).json()
        prof_id = [p for p in profiles if p["mode"] == "combined"][0]["id"]
        resp = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "profile_id": prof_id,
            "files": [
                {"filename": "inv.txt", "content_base64": b64(b"invoice INV-1")},
                {"filename": "grn.txt", "content_base64": b64(b"grn GRN-9")},
            ],
        })
        assert resp.status_code == 201, resp.text
        await run_claimed_job(resp.json()["job_id"], db_session)
        docs = (await client.get(f"/api/v1/projects/{pid}/documents", headers=admin_headers)).json()
        assert len(docs) == 1
        assert docs[0]["extracted_data"]["grn"] == {"n": "GRN-9"}


# --- Submissions ---

class TestSubmissions:
    async def test_get_and_file_content(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        prov = await create_provider(client, admin_headers)
        await create_profile(client, admin_headers, pid, tid, prov)
        patch_adapter(monkeypatch, [INVOICE_JSON])

        resp = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=admin_headers, json={
            "document_type_id": tid,
            "files": [{"filename": "inv.txt", "content_base64": b64(INVOICE_TEXT.encode())}],
        })
        sub_id = resp.json()["submission_id"]
        await run_claimed_job(resp.json()["job_id"], db_session)

        sub = (await client.get(f"/api/v1/submissions/{sub_id}", headers=admin_headers)).json()
        assert len(sub["files"]) == 1
        assert sub["files"][0]["status"] == "extracted"
        assert sub["files"][0]["document_id"]

        content = await client.get(
            f"/api/v1/submissions/{sub_id}/files/{sub['files'][0]['id']}/content",
            headers=admin_headers,
        )
        assert content.status_code == 200
        assert b"INV-001" in content.content

    async def test_viewer_forbidden_submit(self, client: AsyncClient, admin_headers, viewer_headers):
        pid = await create_project(client, admin_headers)
        resp = await client.post(f"/api/v1/projects/{pid}/extract/json", headers=viewer_headers, json={
            "files": [{"filename": "a.txt", "content_base64": b64(b"x")}],
        })
        assert resp.status_code in (400, 403)


# --- Webhooks ---

class TestWebhooks:
    async def test_signature(self):
        from app.services.pipeline import _sign

        sig = _sign("secret", b"{}")
        assert sig.startswith("sha256=")
        assert len(sig) == 7 + 64

    async def test_private_url_rejected(self, client: AsyncClient, admin_headers, db_session):
        from app.services import job_service

        job = await job_service.enqueue(
            db_session, "webhook",
            {"url": "http://127.0.0.1:9/hook", "body": {"a": 1}},
        )
        claimed = await job_service.claim_next(db_session)
        await job_service.run_job(claimed.id)
        await db_session.refresh(job)
        assert job.status == "failed"
        assert "private" in (job.error or "")


# --- Rich prompt contract: schema-in-prompt, {value, confidence} merge ---

RICH_TEXT = "Invoice INV-900\nTotal: 4200\nVendor missing here."
RICH_DATA = {
    "invoice_number": {"value": "INV-900", "confidence": 0.9},
    "total_amount": {"value": 4200, "confidence": 0.85},
    "vendor": {"value": None, "confidence": 0.0},
    "warnings": ["vendor not found"],
    "overall_confidence": 0.8,
}
RICH_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "object"},
        "total_amount": {"type": "object"},
        "vendor": {"type": "object"},
        "warnings": {"type": "array"},
        "overall_confidence": {"type": "number"},
    },
    "required": ["invoice_number", "total_amount"],
}


class TestRichContract:
    async def test_prompt_embeds_schema(self):
        from app.models.extraction_profile import DEFAULT_PROMPTS

        assert "{schema}" in DEFAULT_PROMPTS["extraction"]
        assert "{text}" in DEFAULT_PROMPTS["extraction"]
        assert "JSON" in DEFAULT_PROMPTS["extraction"]

    async def test_pair_merge_min_rule(self):
        from app.services.extraction import ground_signals, map_confidence

        data = {
            "invoice_number": {"value": "INV-900", "confidence": 0.9},
            "total_amount": {"value": 4200, "confidence": 0.99},
            "vendor": {"value": "Ghost Corp", "confidence": 0.95},
        }
        signals = ground_signals(data, RICH_TEXT)
        assert signals["invoice_number"]["pair"] is True
        assert signals["invoice_number"]["model_confidence"] == 0.9
        scores = map_confidence(data, signals, {"found": 0.95, "not_found": 0.4, "retry_penalty": 0.0})
        # grounded (0.95) capped by model (0.9)
        assert scores["invoice_number"] == 0.9
        # model says 0.99 but value IS in text -> min(0.99, 0.95)
        assert scores["total_amount"] == 0.95
        # model confident but value absent from text -> min(0.95, 0.4)
        assert scores["vendor"] == 0.4

    async def test_pair_in_table_row(self):
        from app.services.extraction import ground_signals, map_confidence

        data = {"items": [{"description": {"value": "Widget", "confidence": 0.9}, "qty": 2}]}
        signals = ground_signals(data, "Widget x2")
        scores = map_confidence(data, signals, {"found": 0.95, "not_found": 0.4, "retry_penalty": 0.0})
        assert scores["items"] == [{"description": 0.9, "qty": 0.95}]

    async def test_warnings_and_overall_in_meta(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        import json

        from app.services import extraction as ext_mod

        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, name="Rich", schema=RICH_SCHEMA)
        prov = await create_provider(client, admin_headers)
        prof_id = await create_profile(client, admin_headers, pid, tid, prov)

        profile = await db_session.get(ext_mod.ExtractionProfile, prof_id)
        doc_type = await db_session.get(ext_mod.DocumentType, tid)
        patch_adapter(monkeypatch, [json.dumps(RICH_DATA)])
        result = await ext_mod.extract_one(db_session, profile, doc_type, RICH_TEXT)
        assert result.meta["warnings"] == ["vendor not found"]
        assert result.meta["overall_confidence"] == 0.8
        # vendor pair: model 0.0 + absent -> min() floors at 0.0, still submittable
        assert result.scores["vendor"] == 0.0
        assert result.scores["invoice_number"] == 0.9

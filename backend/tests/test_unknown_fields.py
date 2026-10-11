"""Unknown model-output fields must never reach review as facts."""

import json

import pytest
from httpx import AsyncClient

from tests.test_extraction_m2 import (
    create_doc_type,
    create_profile,
    create_project,
    create_provider,
    patch_adapter,
)

pytestmark = pytest.mark.asyncio

SCHEMA = {
    "type": "object",
    "title": "Invoice",
    "required": ["invoice_number", "total_amount"],
    "properties": {
        "invoice_number": {"type": "string"},
        "total_amount": {"type": "number"},
    },
}

GARBAGE = json.dumps({
    "invoice_number": "INV-9",
    "total_amount": 10.0,
    "currency null, ": "invoice_date null, ",
})

CLEAN = json.dumps({
    "invoice_number": "INV-9",
    "total_amount": 10.0,
})


class TestUnknownFields:
    async def test_degenerate_output_retried_then_clean(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        from app.services import extraction as ext_mod

        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, schema=SCHEMA)
        prov = await create_provider(client, admin_headers)
        prof_id = await create_profile(client, admin_headers, pid, tid, prov)

        profile = await db_session.get(ext_mod.ExtractionProfile, prof_id)
        doc_type = await db_session.get(ext_mod.DocumentType, tid)
        adapter = patch_adapter(monkeypatch, [GARBAGE, CLEAN])
        result = await ext_mod.extract_one(db_session, profile, doc_type, "text")
        assert adapter.calls == 2
        assert set(result.data.keys()) <= {
            "invoice_number", "total_amount", "warnings", "overall_confidence",
        }
        assert result.data["invoice_number"] == "INV-9"

    async def test_persistent_garbage_fails_file(
        self, client: AsyncClient, admin_headers, db_session, monkeypatch
    ):
        from app.services import extraction as ext_mod
        from app.services.extraction import ExtractionFailed

        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, schema=SCHEMA)
        prov = await create_provider(client, admin_headers)
        prof_id = await create_profile(client, admin_headers, pid, tid, prov)

        profile = await db_session.get(ext_mod.ExtractionProfile, prof_id)
        doc_type = await db_session.get(ext_mod.DocumentType, tid)
        patch_adapter(monkeypatch, [GARBAGE])
        with pytest.raises(ExtractionFailed):
            await ext_mod.extract_one(db_session, profile, doc_type, "text")

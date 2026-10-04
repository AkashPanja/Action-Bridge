"""Repro: doc type create with validation_rules 500s on NAS."""

import pytest
from httpx import AsyncClient

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


async def test_create_type_with_rules(
    client: AsyncClient, admin_headers, db_session,
):
    r = await client.post("/api/v1/projects", headers=admin_headers,
                          json={"name": "P"})
    pid = r.json()["id"]
    r = await client.post("/api/v1/regex-patterns", headers=admin_headers,
                          json={"name": "X", "pattern": "^[A-Z]+$",
                                "flags": "", "description": "x"})
    assert r.status_code == 201, r.text
    fpid = r.json()["id"]
    body = {
        "name": "Invoice",
        "confidence_threshold": 0.95,
        "schema_definition": SCHEMA,
        "validation_rules": {
            "invoice_number": {"and_patterns": [{"id": fpid}],
                               "confidence_min": 0.8},
        },
    }
    r = await client.post(f"/api/v1/projects/{pid}/document-types",
                          headers=admin_headers, json=body)
    assert r.status_code == 201, r.text

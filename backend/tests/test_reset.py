"""System reset wipes everything (fresh-install state)."""

import os

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio


async def _counts(db_session):
    from app.models.project import Base

    out = {}
    for table in Base.metadata.sorted_tables:
        out[table.name] = await db_session.scalar(
            select(func.count()).select_from(table))
    return out


class TestSystemReset:
    async def test_reset_clears_all_tables_and_marker(
        self, client: AsyncClient, admin_headers, db_session, setup_complete,
    ):
        from app.config import settings

        # seed representative rows across feature tables
        pid = (await client.post("/api/v1/projects", headers=admin_headers,
                                 json={"name": "ResetProj"})).json()["id"]
        await client.post(f"/api/v1/projects/{pid}/document-types",
                          headers=admin_headers,
                          json={"name": "T", "schema_definition": {
                              "type": "object", "properties": {}}})
        await client.post("/api/v1/regex-patterns", headers=admin_headers,
                          json={"name": "P", "pattern": "^a+$",
                                "flags": "", "description": "d"})
        await client.post("/api/v1/credentials", headers=admin_headers,
                          json={"name": "K", "type": "api_key",
                                "payload": {"api_key": "secret-value"}})
        before = await _counts(db_session)
        assert before.get("projects", 0) >= 1
        assert before.get("users", 0) >= 1
        assert os.path.exists(settings.setup_complete_file)

        resp = await client.post("/api/v1/auth/reset", headers=admin_headers)
        assert resp.status_code == 200

        # new session: committed state must be empty everywhere
        from app.services.job_service import AsyncSessionLocal
        async with AsyncSessionLocal() as fresh:
            after = await _counts(fresh)
        assert all(v == 0 for v in after.values()), after
        assert not os.path.exists(settings.setup_complete_file)

        status = await client.get("/api/v1/auth/status")
        assert status.json()["setup_required"] is True

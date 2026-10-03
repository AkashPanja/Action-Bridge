import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SAMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
        "email": {"type": "string"},
    },
    "required": ["name", "email"],
}


async def create_project(client, headers):
    resp = await client.post("/api/v1/projects", headers=headers, json={"name": "DocTestProj"})
    return resp.json()["id"]


async def create_doc_type(client, headers, project_id, schema=None, validation_rules=None):
    data = {
        "name": "TestDocType",
        "schema_definition": schema or SAMPLE_SCHEMA,
    }
    if validation_rules:
        data["validation_rules"] = validation_rules
    resp = await client.post(f"/api/v1/projects/{project_id}/document-types", headers=headers, json=data)
    return resp.json()["id"]


async def submit_doc(client, headers, project_id, type_id, data=None, confidence_scores=None):
    payload = {
        "extracted_data": data or {"name": "John", "age": 30, "email": "john@test.com"},
    }
    if confidence_scores:
        payload["confidence_scores"] = confidence_scores
    resp = await client.post(
        f"/api/v1/projects/{project_id}/documents/document-types/{type_id}",
        headers=headers,
        json=payload,
    )
    return resp


async def submit_doc_no_auto_approve(client, headers, project_id, type_id, data=None):
    """Submit a doc that fails schema validation to get 'pending_review' status."""
    payload = {
        "extracted_data": data or {"name": "John"},  # missing required 'email' field
    }
    resp = await client.post(
        f"/api/v1/projects/{project_id}/documents/document-types/{type_id}",
        headers=headers,
        json=payload,
    )
    return resp


class TestDocumentSubmission:
    async def test_submit_document(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc(client, admin_headers, pid, tid)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "approved"
        assert data["extracted_data"]["name"] == "John"

    async def test_submit_document_missing_required_field(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc(client, admin_headers, pid, tid, data={"age": 25})
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_submit_document_wrong_type(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc(client, admin_headers, pid, tid, data={
            "name": "John", "age": "notanumber", "email": "john@test.com",
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_submit_document_invalid_type_id(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        resp = await submit_doc(client, admin_headers, pid, "nonexistent")
        assert resp.status_code == 400

    async def test_submit_document_with_api_key(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        key_resp = await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": pid, "label": "BotKey", "scopes": ["documents:write"],
        })
        raw_key = key_resp.json()["raw_key"]
        resp = await client.post(
            f"/api/v1/projects/{pid}/documents/document-types/{tid}",
            headers={"X-API-Key": raw_key},
            json={"extracted_data": {"name": "Bot", "age": 25, "email": "bot@test.com"}},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "approved"


class TestDocumentValidationRules:
    async def test_confidence_min_passed(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "name": {"confidence_min": 0.80},
            "age": {"confidence_min": 0.90},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            confidence_scores={"name": 0.95, "age": 0.92, "email": 0.99},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "approved"

    async def test_confidence_min_failed(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "name": {"confidence_min": 0.80},
            "age": {"confidence_min": 0.95},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            confidence_scores={"name": 0.95, "age": 0.90, "email": 0.99},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_min_length_validation(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "name": {"min_length": 3},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "AB", "age": 25, "email": "a@b.com"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_max_length_validation(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "name": {"max_length": 5},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "TooLongName", "age": 25, "email": "a@b.com"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_pattern_validation(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "email": {"pattern": r".+@.+\..+"},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "John", "age": 25, "email": "invalid"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_min_value_validation(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "age": {"min_value": 18},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "Kid", "age": 15, "email": "kid@test.com"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_max_value_validation(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "age": {"max_value": 120},
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "Old", "age": 150, "email": "old@test.com"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_and_pattern_group(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "email": {
                "and_patterns": [
                    {"pattern": r".+@.+\..+", "negate": False},
                ],
            },
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "John", "age": 25, "email": "invalid"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_or_pattern_group(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "name": {
                "or_patterns": [
                    {"pattern": r"^John$", "negate": False},
                    {"pattern": r"^Jane$", "negate": False},
                ],
            },
        })
        resp = await submit_doc(client, admin_headers, pid, tid,
            data={"name": "Alice", "age": 25, "email": "a@b.com"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"

    async def test_all_validations_pass_auto_approve(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid, validation_rules={
            "name": {"min_length": 1},
            "email": {"pattern": r".+@.+\..+"},
        })
        resp = await submit_doc(client, admin_headers, pid, tid, data={
            "name": "AutoApprove", "age": 30, "email": "auto@test.com",
        }, confidence_scores={"name": 0.99, "age": 0.99, "email": 0.99})
        assert resp.status_code == 201
        assert resp.json()["status"] == "approved"


class TestDocumentFSM:
    async def test_approve_document(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc_no_auto_approve(client, admin_headers, pid, tid)
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"
        doc_id = resp.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{pid}/documents/{doc_id}?actor=admin",
            headers=admin_headers,
            json={"status": "approved", "comment": "Looks good"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_reject_document(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc_no_auto_approve(client, admin_headers, pid, tid)
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending_review"
        doc_id = resp.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{pid}/documents/{doc_id}?actor=reviewer",
            headers=admin_headers,
            json={"status": "rejected", "comment": "Needs work"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    async def test_invalid_transition(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc_no_auto_approve(client, admin_headers, pid, tid)
        doc_id = resp.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{pid}/documents/{doc_id}?actor=admin",
            headers=admin_headers,
            json={"status": "received"},
        )
        assert resp.status_code == 400

    async def test_approve_forbidden_for_viewer(self, client: AsyncClient, admin_headers, viewer_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc_no_auto_approve(client, admin_headers, pid, tid)
        doc_id = resp.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{pid}/documents/{doc_id}?actor=viewer",
            headers=viewer_headers,
            json={"status": "approved"},
        )
        assert resp.status_code == 403


class TestDocumentListAndGet:
    async def test_list_documents(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        await submit_doc(client, admin_headers, pid, tid)
        resp = await client.get(f"/api/v1/projects/{pid}/documents", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    async def test_list_documents_pagination_and_type_names(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        for _ in range(3):
            await submit_doc(client, admin_headers, pid, tid)
        first = (await client.get(
            f"/api/v1/projects/{pid}/documents?limit=2", headers=admin_headers)).json()
        assert len(first) == 2
        assert all(d["document_type_name"] == "TestDocType" for d in first)
        rest = (await client.get(
            f"/api/v1/projects/{pid}/documents?limit=2&offset=2", headers=admin_headers)).json()
        assert len(rest) == 1
        assert {d["id"] for d in first} | {d["id"] for d in rest} == {
            d["id"] for d in (await client.get(
                f"/api/v1/projects/{pid}/documents?limit=10", headers=admin_headers)).json()
        }

    async def test_get_document(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc(client, admin_headers, pid, tid)
        doc_id = resp.json()["id"]
        resp = await client.get(f"/api/v1/projects/{pid}/documents/{doc_id}?include_history=true", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id
        assert resp.json()["history"] is not None

    async def test_get_document_not_found(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        resp = await client.get(f"/api/v1/projects/{pid}/documents/nonexistent", headers=admin_headers)
        assert resp.status_code == 404

    async def test_delete_document(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        resp = await submit_doc(client, admin_headers, pid, tid)
        doc_id = resp.json()["id"]
        resp = await client.delete(f"/api/v1/projects/{pid}/documents/{doc_id}", headers=admin_headers)
        assert resp.status_code == 204

    async def test_bulk_delete_documents(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        tid = await create_doc_type(client, admin_headers, pid)
        d1 = await submit_doc(client, admin_headers, pid, tid)
        d2 = await submit_doc(client, admin_headers, pid, tid)
        resp = await client.post(f"/api/v1/projects/{pid}/documents/bulk-delete", headers=admin_headers, json={
            "ids": [d1.json()["id"], d2.json()["id"]],
        })
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2


class TestDocumentTypeCRUD:
    async def test_create_document_type(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        resp = await client.post(f"/api/v1/projects/{pid}/document-types", headers=admin_headers, json={
            "name": "Invoice",
            "schema_definition": SAMPLE_SCHEMA,
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "Invoice"

    async def test_list_document_types(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        await client.post(f"/api/v1/projects/{pid}/document-types", headers=admin_headers, json={
            "name": "DT1", "schema_definition": SAMPLE_SCHEMA,
        })
        await client.post(f"/api/v1/projects/{pid}/document-types", headers=admin_headers, json={
            "name": "DT2", "schema_definition": SAMPLE_SCHEMA,
        })
        resp = await client.get(f"/api/v1/projects/{pid}/document-types", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_document_type(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        cr = await client.post(f"/api/v1/projects/{pid}/document-types", headers=admin_headers, json={
            "name": "GetDT", "schema_definition": SAMPLE_SCHEMA,
        })
        tid = cr.json()["id"]
        resp = await client.get(f"/api/v1/projects/{pid}/document-types/{tid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetDT"

    async def test_delete_document_type(self, client: AsyncClient, admin_headers):
        pid = await create_project(client, admin_headers)
        cr = await client.post(f"/api/v1/projects/{pid}/document-types", headers=admin_headers, json={
            "name": "DeleteDT", "schema_definition": SAMPLE_SCHEMA,
        })
        tid = cr.json()["id"]
        resp = await client.delete(f"/api/v1/projects/{pid}/document-types/{tid}", headers=admin_headers)
        assert resp.status_code == 204

"""intake_files: empty batches must not crash; every file gets its own row."""

import pytest
import pytest_asyncio
from sqlalchemy import select

pytestmark = pytest.mark.asyncio

from app.models.project import Project
from app.models.submission import SubmissionFile
from app.services import pipeline


@pytest_asyncio.fixture
async def project_id(db_session):
    p = Project(name="IntakeProj")
    db_session.add(p)
    await db_session.commit()
    return p.id


class TestIntakeFiles:
    async def test_empty_files_no_crash_no_rows(self, db_session, project_id):
        sub = await pipeline.intake_files(
            db_session, project_id, "email", [],
            idempotency_key="k-empty",
        )
        assert sub.id is not None
        rows = (await db_session.execute(
            select(SubmissionFile).where(SubmissionFile.submission_id == sub.id)
        )).scalars().all()
        assert rows == []

    async def test_multi_file_creates_row_per_file(self, db_session, project_id):
        sub = await pipeline.intake_files(
            db_session, project_id, "upload",
            [("a.pdf", b"%PDF-1.4 a"), ("b.pdf", b"%PDF-1.4 b")],
            idempotency_key="k-multi",
        )
        rows = (await db_session.execute(
            select(SubmissionFile)
            .where(SubmissionFile.submission_id == sub.id)
            .order_by(SubmissionFile.filename)
        )).scalars().all()
        assert [r.filename for r in rows] == ["a.pdf", "b.pdf"]
        assert {r.sha256 for r in rows} == {
            __import__("hashlib").sha256(b"%PDF-1.4 a").hexdigest(),
            __import__("hashlib").sha256(b"%PDF-1.4 b").hexdigest(),
        }
        assert all(r.status == "pending" for r in rows)

import asyncio
import os
import tempfile
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "actionbridge_test.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DEBUG"] = "false"
if not os.environ.get("APP_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet

    os.environ["APP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models import Base
from app.auth.models import User
from app.auth.service import create_access_token, hash_password

TEST_SETUP_FILE = ".test-setup-complete"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        if "sqlite" in str(engine.url):
            await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.run_sync(Base.metadata.drop_all)
        if "sqlite" in str(engine.url):
            await conn.execute(text("PRAGMA foreign_keys=ON"))


@pytest_asyncio.fixture
async def client() -> AsyncGenerator:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def setup_complete(db_session):
    from app.config import settings
    original = settings.setup_complete_file
    settings.setup_complete_file = TEST_SETUP_FILE
    open(TEST_SETUP_FILE, "w").close()
    db_session.add(User(
        email="setup@test.com",
        password_hash="x",
        name="Setup User",
        role="admin",
    ))
    await db_session.commit()
    yield
    settings.setup_complete_file = original
    if os.path.exists(TEST_SETUP_FILE):
        os.remove(TEST_SETUP_FILE)


@pytest_asyncio.fixture
async def admin_user(db_session) -> User:
    user = User(
        email="admin@test.com",
        password_hash=hash_password("admin123"),
        name="Admin User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user) -> str:
    return create_access_token({
        "sub": admin_user.id,
        "role": admin_user.role,
        "email": admin_user.email,
    })


@pytest_asyncio.fixture
async def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def editor_user(db_session) -> User:
    user = User(
        email="editor@test.com",
        password_hash=hash_password("editor123"),
        name="Editor User",
        role="editor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def editor_token(editor_user) -> str:
    return create_access_token({
        "sub": editor_user.id,
        "role": editor_user.role,
        "email": editor_user.email,
    })


@pytest_asyncio.fixture
async def editor_headers(editor_token) -> dict:
    return {"Authorization": f"Bearer {editor_token}"}


@pytest_asyncio.fixture
async def viewer_user(db_session) -> User:
    user = User(
        email="viewer@test.com",
        password_hash=hash_password("viewer123"),
        name="Viewer User",
        role="viewer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_token(viewer_user) -> str:
    return create_access_token({
        "sub": viewer_user.id,
        "role": viewer_user.role,
        "email": viewer_user.email,
    })


@pytest_asyncio.fixture
async def viewer_headers(viewer_token) -> dict:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def setup_required():
    from app.config import settings
    original = settings.setup_complete_file
    settings.setup_complete_file = TEST_SETUP_FILE
    if os.path.exists(TEST_SETUP_FILE):
        os.remove(TEST_SETUP_FILE)
    yield
    settings.setup_complete_file = original
    if os.path.exists(TEST_SETUP_FILE):
        os.remove(TEST_SETUP_FILE)

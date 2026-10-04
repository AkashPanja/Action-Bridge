import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.middleware.ratelimit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.models import Base
from app.routers import (
    attachments,
    comments,
    credentials,
    document_types,
    documents,
    extract,
    invitations,
    jobs,
    llm_providers,
    notifications,
    processing,
    profiles,
    projects,
    prompt_templates,
    regex_patterns,
    settings as settings_router,
    submissions,
    subscriptions,
    triggers,
)

from .auth.router import router as auth_router

logger = logging.getLogger("app.main")

DEFAULT_SECRET = "change-me-in-production-use-a-long-random-string"


def ensure_production_secrets() -> None:
    if not settings.debug and settings.secret_key == DEFAULT_SECRET:
        raise RuntimeError(
            "Refusing to start with the default SECRET_KEY outside debug mode. "
            "Set a strong SECRET_KEY."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_production_secrets()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        # FR-2.2: refuse to start when credentials exist but no master key.
        from sqlalchemy import select

        from app.models.credential import Credential
        from app.services.provider_service import ensure_default_provider

        count = (await db.execute(select(Credential.id).limit(1))).first()
        if count and not os.getenv("APP_ENCRYPTION_KEY"):
            raise RuntimeError(
                "Credentials exist but APP_ENCRYPTION_KEY is not set. Refusing to start."
            )
        seeded = await ensure_default_provider(db)
        if seeded:
            logger.info("Seeded default provider '%s' (%s).", seeded.name, seeded.model)
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    # Interactive docs only in debug; they expose the full API surface.
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.debug else None,
)

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(projects.router)
app.include_router(document_types.router)
app.include_router(documents.router)
app.include_router(credentials.router)
app.include_router(llm_providers.router)
app.include_router(processing.router)
app.include_router(profiles.router)
app.include_router(prompt_templates.router)
app.include_router(extract.router)
app.include_router(submissions.router)
app.include_router(jobs.router)
app.include_router(regex_patterns.router)
app.include_router(settings_router.router)
app.include_router(notifications.router)
app.include_router(comments.router)
app.include_router(invitations.router)
app.include_router(subscriptions.router)
app.include_router(attachments.router)
app.include_router(triggers.router)

# Serve uploaded files
uploads_path = os.path.abspath(settings.upload_dir)
os.makedirs(uploads_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}

<div align="center">

# Action Bridge

### The human-in-the-loop layer for RPA teams

Bots submit documents via API. Humans review, approve, or reject them through a clean web UI —
all validated against dynamic JSON Schemas per document type.

[![CI](https://github.com/AkashPanja/Action-Bridge/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/AkashPanja/Action-Bridge/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Node 20+](https://img.shields.io/badge/node-20%2B-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/frontend-React%2018-61DAFB.svg)](https://react.dev/)
[![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-orange.svg)](#license)

[Features](#features) · [Quick Start](#quick-start) · [Configuration](#configuration) · [API Overview](#api-overview) · [Project Structure](#project-structure) · [Testing](#testing) · [License](#license)

</div>

---

## Features

| Area | What you get |
|---|---|
| **Schema Builder** | Define document types visually (drag-and-drop fields) or via raw JSON, with undo/redo |
| **Document Lifecycle** | Full state machine — `received → pending_review → approved / rejected` — with audit trail |
| **Confidence Scoring** | Per-field confidence heatmap (green ≥ 85%, amber ≥ 70%, red < 70%) |
| **RPA Bot Integration** | Submit documents programmatically with `X-API-Key` or Bearer JWT |
| **Review Workflow** | Comments, file attachments, notifications, and watch subscriptions per document |
| **Validation Patterns** | Reusable regex rules for field-level validation |
| **Access Control** | Admin / Reviewer / Viewer roles with granular UI permission gating |
| **API Keys** | Scoped, revocable per-project keys for bot integration |
| **Email Notifications** | SMTP-powered alerts (Gmail-ready) plus a built-in test-email tool |
| **Password Reset** | Self-service forgot-password flow with expiring email links |
| **Setup Wizard** | WordPress-style first-run admin creation with optional SMTP setup |
| **Dashboard** | Per-project stats: volume, approval rates, daily charts, avg. confidence |
| **Import / Export** | CSV and Excel export of document data |
| **Dark Mode** | Full dark theme with glass-morphism design |

## How It Works

```mermaid
flowchart LR
    BOT[RPA Bot] -- "POST documents (API key)" --> API[FastAPI Backend]
    API -- "validate vs JSON Schema" --> DB[(PostgreSQL / SQLite)]
    HUMAN[Reviewer] -- "review / approve / reject" --> UI[React Frontend]
    UI -- "REST API (JWT)" --> API
    API -- "SMTP alerts" --> MAIL[Email]
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Pydantic v2, Alembic |
| Database | PostgreSQL (production) / SQLite (development) |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, Framer Motion, Radix UI |
| Auth | Self-contained JWT (email/password) + `X-API-Key` for bots |
| Email | SMTP (STARTTLS / implicit TLS) with HTML + plain-text templates |
| Infrastructure | Docker Compose (PostgreSQL + API + frontend) |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- (Optional) Docker, for the production-style PostgreSQL setup

### Option A — One command (Windows, fastest dev loop)

```powershell
./dev.ps1          # starts API :8000 (auto-reload) + web :5173 (hot reload)
./dev.ps1 -Kill    # stops both
```

### Option B — Manual

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Visit **http://localhost:5173** — the setup wizard will guide you through creating the admin account.
There are no default credentials.

### Option C — Docker (PostgreSQL + API + frontend)

```bash
docker compose up -d
```

Set `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/actionbridge` in `backend/.env`
(or via environment when using the published images).

### RPA Bot Integration

```bash
# Submit a document via API key
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/documents/document-types/{type_id} \
  -H "X-API-Key: dc_your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "extracted_data": {"invoice_number": "INV-001", "total_amount": 150.00},
    "confidence_scores": {"invoice_number": 0.98, "total_amount": 0.95}
  }'
```

API keys are generated from **Project → API Keys** (admin only).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./doc_action_center.db` | Async DB URL (PostgreSQL via `postgresql+asyncpg://…`) |
| `SECRET_KEY` | `change-me-…` | JWT signing key — **change in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | Login session lifetime |
| `DEBUG` | `True` | Enables SQL echo logging and verbose errors |
| `FRONTEND_URL` | `http://localhost:5173` | Base URL used in email links (password reset) |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed browser origins (comma-separated) |
| `UPLOAD_DIR` | `./uploads` | Attachment storage directory |

SMTP is configured from the UI (**Settings → SMTP**), including Gmail (ports 587 STARTTLS / 465 SSL).
Use **Send test email** to verify delivery before relying on notifications.

## Project Structure

```
backend/
├── app/
│   ├── auth/          # JWT login, API keys, permissions, password reset
│   ├── models/        # SQLAlchemy models (projects, documents, comments, …)
│   ├── routers/       # FastAPI route handlers
│   ├── schemas/       # Pydantic request/response schemas
│   ├── services/      # Business logic (documents, email, subscriptions, …)
│   ├── config.py      # Settings (env-driven)
│   └── main.py        # FastAPI entry point
├── alembic/           # Database migrations
├── tests/             # Pytest suite (107 tests)
└── requirements.txt

frontend/
├── src/
│   ├── components/    # UI primitives, layout, schema builder
│   ├── contexts/      # Auth context
│   ├── hooks/         # React Query hooks
│   ├── lib/           # API client, RBAC helpers
│   ├── pages/         # Projects, documents, settings, auth (incl. password reset)
│   ├── router/        # Route definitions
│   └── test/          # Vitest suite (26 tests)
├── vite.config.ts
└── package.json
```

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/auth/status` | Check if setup is required |
| `POST` | `/api/v1/auth/setup` | Create initial admin account |
| `POST` | `/api/v1/auth/login` | Login with email/password |
| `GET` | `/api/v1/auth/me` | Get current user |
| `POST` | `/api/v1/auth/password-reset` | Request password-reset email |
| `POST` | `/api/v1/auth/password-reset/confirm` | Confirm reset with token |
| `GET` | `/api/v1/auth/users` | List users (admin) |
| `PATCH` | `/api/v1/auth/users/{id}` | Update user role/status (admin) |
| `GET/POST/DELETE` | `/api/v1/auth/api-keys` | Manage API keys (admin) |
| `GET/POST` | `/api/v1/projects` | List / create projects |
| `GET` | `/api/v1/projects/{id}/stats` | Project dashboard stats |
| `GET/POST` | `/api/v1/projects/{id}/document-types` | List / create document types |
| `GET` | `/api/v1/projects/{id}/documents` | List documents (inbox) |
| `POST` | `/api/v1/projects/{id}/documents/document-types/{type_id}` | Submit document (bot) |
| `PATCH` | `/api/v1/projects/{id}/documents/{doc_id}` | Update / approve / reject |
| `GET/PATCH` | `/api/v1/settings` | App settings incl. SMTP (admin) |
| `POST` | `/api/v1/settings/test-email` | Send a test email (admin) |

Full interactive docs are served by the API at **http://localhost:8000/docs**.

## Testing

```bash
# Backend — 107 tests (~50s)
cd backend
python -m pytest tests/ -q

# Frontend — 26 tests
cd frontend
npm test
```

Backend tests use an isolated SQLite database in the OS temp directory, so your dev
database is never touched.

## License

**Action Bridge Non-Commercial License** — see [LICENSE](LICENSE) for the full text.

In short:

- **You may** use, copy, modify, and share this software — free of charge — for personal use, internal business use, education, and research.
- **You may not** sell it, offer it as a paid hosted service, bundle it into a product sold for profit, or sublicense it under different terms.
- **Commercial use requires prior written permission.**

Copyright © 2026 Akash Panja

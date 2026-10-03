# Action Bridge — Requirements (consolidated)

Single source of truth for product requirements. Requirement IDs (`FR-x`) are for traceability.

**Status legend:** ✅ Done · ◐ Partial · 🔲 Pending

**Changelog**
- v1.0 — Original extraction & email-ingestion spec.
- v1.1 — PM review: code-verified open items, auto-approve conflict (FR-8.1a), nested-confidence rule (R3), provider call log (FR-1.8).
- v1.2 — Consolidated with the platform baseline; OAuth-first + IMAP fallback (A1), per-trigger import window (A2), ingest-and-skip taxonomy (A3), intake wizard + connection health (FR-8.6); status-marked every item.

**Stack:** FastAPI, SQLAlchemy async, Pydantic v2, PostgreSQL/SQLite, Alembic, React 18 + Vite + TypeScript + Tailwind, JWT + `X-API-Key` auth, roles Admin/Reviewer/Viewer.

---

## Part A — Existing platform (baseline, all ✅ Done)

The review platform that everything new connects to. No changes required here except where noted.

- **A-FR-1** Projects (create, manage, dashboard stats). ✅
- **A-FR-2** Document types with Draft-7 JSON Schema definitions + regex validation rules. ✅
- **A-FR-3** Review lifecycle via `submit_document()` (`backend/app/services/document_service.py:153`): `received` → auto-`approved` if schema-clean, else `pending_review` → human `approved`/`rejected`, with audit trail. ✅
- **A-FR-4** Numeric per-field `confidence_scores` (0–1, required for every field) + confidence heatmap (green ≥ 85%, amber ≥ 70%, red < 70%). ✅
- **A-FR-5** Auth: JWT login, `dc_`-prefixed per-project API keys, RBAC (`PERMISSION_MAP`). ✅
- **A-FR-6** Attachments (upload/list/delete, served under `/uploads`); review UI links files (no inline preview — see FR-8.4). ✅ / 🔲 (preview pending)
- **A-FR-7** Comments, notifications, subscriptions, invitations, members. ✅
- **A-FR-8** SMTP email notifications + test-email tool; password-reset flow with expiring links. ✅
- **A-FR-9** Setup wizard, user management, API-key management, dark mode, CSV/XLSX export. ✅

**Connectivity contract (binding on all new work):** new intake objects reference existing
`projects` and `document_types` by foreign key; extracted documents are created through the
existing `submit_document()`; validation reuses existing schemas; correction happens in the
existing inbox/review UI. No duplicated lifecycle, auth, or review logic.

---

## Part B — AI extraction & email ingestion

### B1. Purpose

Add an automatic front end to the human-in-the-loop review flow. Documents arrive by email
(Outlook, Gmail, IMAP), manual upload, or RPA API call. The system reads them, optionally
classifies them, extracts data as custom JSON using prompts, and sends the result into the
existing review lifecycle.

The model layer is pluggable: a local model by default, cloud models when the user allows them.

### B2. Owner decisions (locked)

1. Local model: **Qwen2.5 3B** (text only) served by Ollama. Cloud: Claude, OpenAI, OpenAI-compatible APIs, OpenRouter, remote Ollama.
2. Works for **any document type** with **no training** — behaviour via prompts + existing JSON schemas.
3. Confidence handling already exists; the extractor feeds it, never reinvents it.
4. Related-document matching (invoice + GRN) is prompt-driven: all files of one email go to the LLM as a single input; one custom JSON comes back.
5. One multi-page PDF = **one document** (no page splitting).
6. **Multiple mailboxes** supported.
7. Volume, cloud-vs-local, privacy are **user-configurable**.
8. UI must include: processing-parallelism setting, **credentials manager**, **trigger manager**.
9. RPA bots can call extraction through the API.
10. **A1 — Auth is both:** OAuth-first (Microsoft Graph for Outlook, Gmail API for Gmail) **plus** IMAP + app-password fallback (Gmail/personal servers). Three connector implementations: `graph`, `gmail_api`, `imap`.
11. **A2 — Import window is a per-trigger option:** last 24 hours / 7 days (default) / 30 days / custom date / unread-only, chosen at connect time.
12. **A3 — Ingest, then skip with reason:** every matched email creates a submission (metadata preserved); files that can't be processed get an explicit skip reason. Nothing vanishes silently.
13. **Single project model:** no duplicate "projects" on the new side. An **Intake link** (mailbox trigger + extraction profile) binds to exactly one existing review project, created via a guided wizard.

### B3. Out of scope for this iteration

Local OCR models (WeVisDoc, GLM-OCR, PaddleOCR-VL), specialist extractors (NuExtract, LFM2-Extract), the Laya classifier, page-level splitting of mixed PDFs, 3-way matching logic outside prompts, bounding-box highlighting. Interfaces must allow adding these later without rewrites (FR-1.4).

### B4. Pipeline overview

```
Sources:  Outlook (Graph/OAuth) | Gmail (API/OAuth or IMAP) | IMAP mailbox
          | Manual upload (UI) | RPA API call
              |
        Submission per email / upload batch / API call
        (idempotent on Message-ID / idempotency key; A3: always created)
              |
        Files stored, filtered (type, size, noise), de-duplicated (SHA-256),
        unprocessable files marked with skip reasons
              |
        Queue: one job per file (per_attachment) or per submission (combined)
              |
        Text acquisition per file (PDF text layer, else OCR provider)
              |
        Extraction Profile decides the mode:
          per_attachment: [classify] -> extract, one document per file
          combined:       all files merged into ONE LLM input -> one JSON
              |
        Validate JSON against schema (retry once, then fallback or fail)
              |
        Grounding checks -> signals mapped to EXISTING confidence numbers
              |
        Create Document in the existing review flow (forced pending_review)
              |
        Webhook / job status for API callers
```

All work runs as **jobs** in the M1 database-backed queue with a worker.

### B5. Functional requirements

#### LLM providers

- **FR-1.1** Admin defines providers: name, kind, base URL, credential ref, model, capability flags (`vision`, `json_schema`, `json_object`), max concurrency, timeout, `is_local`. ✅ Done (M1)
- **FR-1.2** Two adapters: `openai_compatible`, `anthropic`. Model names user-entered, never hard-coded. ✅ Done (M1)
- **FR-1.3** Structured-output order: JSON-schema → JSON-object → prompt-only; result always schema-validated. ✅ Done (M1)
- **FR-1.4** Provider interface (`complete(messages, schema, images?)`) for future adapters. ✅ Done (M1)
- **FR-1.5** "Test provider": tiny prompt → success, latency, JSON-mode report. ✅ Done (M1)
- **FR-1.6** Seeded default: Ollama `http://localhost:11434/v1`, model `actionbridge-qwen25-3b`, `is_local`, concurrency 1. ✅ Done (M1)
- **FR-1.7** Tokens in/out recorded per call (cost optional). ✅ Done (M1)
- **FR-1.8** Append-only `provider_calls` log (provider, job, local flag, latency, tokens, ok/error) for the M4 local-only audit. ✅ Done (M1)

#### Credentials manager

- **FR-2.1** Named credentials: `api_key`, `basic`, `oauth2`; secret fields + notes. ✅ Done (M1)
- **FR-2.2** Fernet/AES-GCM at rest; master key from `APP_ENCRYPTION_KEY` env only; refuse startup when credentials exist without it. ✅ Done (M1)
- **FR-2.3** Write-only secrets; masked hint (last 4) only; update = replace. ✅ Done (M1)
- **FR-2.4** "Test connection" per type (LLM ping, IMAP login; OAuth via provider flow). ✅ Done (M1, OAuth deep-test pending FR-2.7)
- **FR-2.5** Admin-only; audit log on create/update/delete/use, no secret values. ✅ Done (M1)
- **FR-2.6** Providers and triggers reference by id; deleting in-use is blocked. ◐ Partial (providers enforced ✅; triggers land in M3)
- **FR-2.7** OAuth lifecycle: authorize URL, callback, refresh-on-401, disconnect; refresh tokens encrypted. 🔲 Pending (M3)

#### Processing settings

- **FR-3.1** Global settings: CPU workers, max jobs in flight, default retries, default timeout. ✅ Done (M1)
- **FR-3.2** Per-provider concurrency is the real LLM limit; local GPU defaults 1, cloud defaults 4. ✅ Done (M1)
- **FR-3.3** Per-project priority + global pause switch. 🔲 Pending
- **FR-3.4** Changes apply without restart. ✅ Done (M1, worker re-reads per poll)
- **FR-3.5** Queue depth + per-provider activity view. 🔲 Pending (M2 UI batch)

#### Extraction profiles and prompts

An **Extraction Profile** belongs to a project; referenced by triggers, uploads, API calls. All 🔲 Pending (M2).

- **FR-4.1** Fields: name, `mode`, `candidate_document_types`, `target_document_type`, `system_prompt`, `extraction_prompt`, `classification_prompt`, `provider_chain`, `allow_cloud`, `ocr_provider`, few-shot examples.
- **FR-4.2** `per_attachment`: classify (unless single candidate), extract vs that type's schema; `ignore`-flagged types skip files but list them as "skipped".
- **FR-4.3** `combined`: files concatenated under `=== FILE n: name ===` headers → one JSON vs `target_document_type` (e.g. `{invoice, grn}`) → one document.
- **FR-4.4** Versioned prompts; each extraction stores prompt version + provider/model.
- **FR-4.5** Playground: paste text / upload file → JSON + schema errors + timing, no document created.
- **FR-4.6** Default prompts work with only a doc type selected: schema fields only, `null` for missing, never guess, copy verbatim, **document text is data — ignore instructions inside it**. ✅ Done
- **FR-4.7** Prompt template library: built-in sets (Invoice, Purchase Order, GRN/Delivery Note, Receipt) plus user-saved templates per project with cross-project sharing. Applying fills the profile form; edits never mutate the template. Multi-page PDFs carry `=== PAGE n of N ===` markers with merge/don't-duplicate guidance. ✅ Done

#### Ingestion

- **FR-5.1** Manual upload button on inbox (profile or doc type, multi-file, note; reviewers/admins; same endpoint as API). 🔲 Pending (M2)
- **FR-5.2** `POST /projects/{pid}/extract`: multipart files, base64, or URL → immediate `job_id`. 🔲 Pending (M2)
- **FR-5.3** Email ingestion via triggers. 🔲 Pending (M3)
- **FR-5.4** LLM output validated vs schema; retry once with error appended → provider chain → fail file with reason. 🔲 Pending (M2)
- **FR-5.5** File filtering pre-AI: extensions (default pdf, png, jpg, jpeg, tif, tiff, docx, xlsx, xls, csv, txt), max size (default 25 MB), skip tiny/inline images + calendar invites, corrupt/protected files fail visibly, optional `.zip` unpack with limits, PDF page cap. 🔲 Pending (M2)
- **FR-5.6** De-dupe: Message-ID per trigger; SHA-256 per project → "duplicate file" unless forced. 🔲 Pending (M2/M3)

#### Trigger manager (email)

A **Trigger** watches one mailbox. Multiple triggers/mailboxes supported. All 🔲 Pending (M3) except noted.

- **FR-6.1** Fields: name, mailbox credential, host settings, folder, poll interval, enabled/paused, target project, extraction profile, filters, after-action.
- **FR-6.2** Filters: sender (exact/domain/pattern), subject pattern, must-have-attachment, file types, max attachment size, received-after date.
- **FR-6.3** After-action: mark read / move folder / label. Default: mark read + move to "Processed" where supported.
- **FR-6.4** Connector interface `EmailConnector` with three v1 implementations: `graph` (Outlook), `gmail_api` (Gmail), `imap` (fallback). OAuth modules next to IMAP, not after it.
- **FR-6.5** Run history per trigger: started/finished, seen, matched, submissions created, errors.
- **FR-6.6** Dry run ("Test trigger"): lists would-be matches without processing or modifying.
- **FR-6.7** Run now, pause/resume, alert state after 5 consecutive failures with exponential backoff.
- **FR-6.8** Submission keeps email metadata (Message-ID, from/to, subject, date, truncated plain body, attachment list); visible to reviewers.
- **FR-6.9** Generic trigger `type = email` so folder-watcher/scheduler plug in later.
- **FR-6.10** Gmail specifics: OAuth2 user-consent (plus IMAP/app-password fallback); scopes `gmail.readonly` + `gmail.modify`; Drive-linked attachments downloaded via Drive API (extra `drive.readonly` scope at consent); labels for after-actions; initial import window per A2.
- **FR-6.11** Outlook specifics: Microsoft Graph + OAuth2 (no IMAP — basic auth is dead on 365); scopes `Mail.ReadWrite` (+ `Files.Read` for OneDrive links); move/mark-read via Graph; initial import window per A2.

#### Pipeline details (M2 unless noted)

1. **Text acquisition.** PDFs via PyMuPDF text layer; < ~50 chars/page ⇒ scanned. docx/xlsx/csv/txt → direct text. Images + scanned PDFs → profile `ocr_provider`. 🔲
2. **OCR this iteration:** vision-capable cloud provider (`vision = true`) transcribes pages to Markdown (PDF pages rendered at 150–200 DPI). If `allow_cloud = false`, file goes to review as `extraction_failed: needs manual entry`, original viewable. `OcrProvider` interface for future local OCR. 🔲
3. **Context limits:** estimate tokens first; skip to next provider in chain if input won't fit (reserve schema + output room); else fail `input_too_long`. 🔲
4. **Classification** (per_attachment, >1 candidate): subject + filename + first ~1,000 tokens → constrained to candidate names + `other`; `other` follows profile rule (ignore or unclassified review). 🔲
5. **Extraction:** one call, schema + prompts + text, temperature 0. 🔲
6. **Validation + retry** (FR-5.4). 🔲
7. **Grounding checks:** normalize each leaf (whitespace, case, separators, dates) and verify occurrence in source text; run schema/rule checks (totals, date validity). Output `{found, schema_ok, retries}` per field. 🔲
8. **Hand-off** (§B5.8). 🔲

#### Review hand-off, confidence, and intake connectivity

- **FR-8.1** Create through existing `submit_document()` — lifecycle, audit, notifications, RBAC unchanged; no duplicated logic. 🔲 Pending (M2)
- **FR-8.1a** Force `pending_review` for extractor-created documents (skip auto-approve when `actor="extractor"`). Code-verified: clean docs otherwise auto-approve and bypass humans. 🔲 Pending (M2)
- **FR-8.1b** Auto-approve on high confidence: when every field scores at or above `auto_approve_threshold` (global processing setting, default **0.92**, 0 disables), extractor documents take the normal auto-approve path. Validation/schema issues always route to humans regardless of scores. ✅ Done
- **FR-8.2** Extractor supplies `extracted_data` + grounding signals; existing confidence logic scores. Signal→number mapping table (configurable; defaults: found = high, not found = low, retry = reduced — owner to tune). Code-verified mandatory: `submit_document()` rejects non-numeric/missing scores. 🔲 Pending (M2)
- **FR-8.3** Store per document: submission id, source, model/provider, prompt version, token usage, processing time, grounding signals (`extraction_meta`). 🔲 Pending (M2; needs migration adding nullable `submission_id`, `source`, `extraction_meta` to `documents`)
- **FR-8.4** Original-file viewer (PDF/image preview + download) beside extracted fields. Code-verified: links exist, inline preview does not — build it. 🔲 Pending (M2)
- **FR-8.5** Email panel on email-sourced docs: subject, sender, skipped files, one-click "process this file as \<type\>". 🔲 Pending (M3)
- **FR-8.6** Intake wizard + connection health: guided flow (project → doc type → profile → mailbox → window → dry run); project page shows "Connected inboxes" with trigger state/last run/errors. 🔲 Pending (M3)

#### Jobs

- **FR-9.1** States `queued, running, succeeded, failed, retrying, cancelled`; attempts, last error, provider, timings. ✅ Done (M1)
- **FR-9.2** Jobs page (project + global): filters, details, Retry/Cancel. 🔲 Pending (M2 UI batch)
- **FR-9.3** Exponential backoff, transient-only retries; validation failures follow FR-5.4. ✅ Done (M1)
- **FR-9.4** Restart survival: `running` jobs re-queued on startup. ✅ Done (M1)

### B6. Data model (Alembic migrations)

| Table | Key fields | Status |
|---|---|---|
| `credentials` | id, name, type, encrypted_payload, hint, created_by, timestamps (+ non-secret `meta`) | ✅ Done (008) |
| `llm_providers` | id, name, kind, base_url, credential_id, model, vision, json_schema, json_object, max_concurrency, timeout_s, is_local, context_window, enabled | ✅ Done (008) |
| `provider_calls` | provider, job, local flag, latency, tokens, ok/error, timestamp (FR-1.8) | ✅ Done (008) |
| `processing_settings` | scope (global / project), values (JSON) | ✅ Done (008) |
| `jobs` | id, project_id, submission_id\*, kind, status, attempts, error, provider_id, payload/result/usage, timings | ✅ Done (008; \*submission FK lands in M2) |
| `extraction_profiles` | project_id, name, mode, candidate_types, target_document_type_id, prompts, provider_chain, ocr_provider_id, allow_cloud, version | 🔲 M2 |
| `triggers` | project_id, type, name, credential_id, config JSON, profile_id, enabled, state, last_run_at, import window | 🔲 M3 |
| `trigger_runs` | trigger, started/finished, seen, matched, created, error | 🔲 M3 |
| `submissions` | project, source, trigger/profile refs, email_meta JSON, actor/key, idempotency_key | 🔲 M2 |
| `submission_files` | submission, filename, mime, size, sha256, paths, text_source, status, skip_reason, detected_type | 🔲 M2 |
| `documents` += | `submission_id`, `source`, `extraction_meta` (nullable) | 🔲 M2 |

Files live on disk under a configurable root, never in the DB.

### B7. API (`/api/v1`; JWT or `X-API-Key`; status)

| Method | Endpoint | Purpose | Status |
|---|---|---|---|
| `GET/POST/PATCH/DELETE` | `/credentials`, `/credentials/{id}` | Manage credentials (admin) | ✅ M1 |
| `POST` | `/credentials/{id}/test` | Test connection | ✅ M1 |
| `GET` | `/credentials/oauth/{p}/authorize`, `.../callback` | OAuth connect/disconnect (FR-2.7) | 🔲 M3 |
| `GET/POST/PATCH/DELETE` | `/llm-providers`, `/llm-providers/{id}` | Manage providers | ✅ M1 |
| `POST` | `/llm-providers/{id}/test` | Test provider | ✅ M1 |
| `GET/POST/PATCH/DELETE` | `/projects/{pid}/profiles` | Extraction profiles | 🔲 M2 |
| `POST` | `/projects/{pid}/profiles/{id}/playground` | Test run, no document | 🔲 M2 |
| `GET/POST/PATCH/DELETE` | `/projects/{pid}/triggers` | Triggers | 🔲 M3 |
| `POST` | `/projects/{pid}/triggers/{id}/test` | Dry run | 🔲 M3 |
| `POST` | `/projects/{pid}/triggers/{id}/run`, `/pause`, `/resume` | Control | 🔲 M3 |
| `GET/PUT` | `/settings/processing` | Global parallelism | ✅ M1 |
| `POST` | `/projects/{pid}/extract` | **RPA/manual entry point** (`profile_id` or `document_type_id` or `auto`, `idempotency_key`, `callback_url`, `wait_seconds` ≤ 60, `metadata`) → `202 {job_id, submission_id, status}`; webhook HMAC-signed with backoff; same idempotency key never duplicates | 🔲 M2 |
| `GET` | `/jobs/{id}`, `/projects/{pid}/jobs` | Status and list | ✅ M1 |
| `POST` | `/jobs/{id}/retry`, `/jobs/{id}/cancel` | Job actions | ✅ M1 |

### B8. UI requirements (all 🔲 pending: M1 screens join the M2 UI batch)

1. Settings → Providers & Models (list/add/edit/test/concurrency/flags/local badge).
2. Settings → Credentials (masked hints, add/replace, test, usage).
3. Settings → Processing (parallelism, queue depth — needs FR-3.5, pause switch).
4. Project → Profiles (modes, types, prompts, chain, allow-cloud, playground).
5. Project → Triggers + intake wizard (state, last run, editor, dry run, history, import window).
6. Inbox: Upload button, source badge, email panel + skipped files, original-file viewer.
7. Jobs page: filters, errors, retry/cancel.
8. Follow existing glass-morphism, dark-mode, permission gating.

### B9. Security and privacy

- **FR-S1 Cloud gating:** `allow_cloud = false` never calls non-local providers — enforced in provider selection, not just UI; log every call with provider + off-machine flag. 🔲 (enforcement M2; logging ✅ via `provider_calls`)
- **FR-S2 Prompt-injection hardening:** delimiters, untrusted-data system prompt, no tools, schema-validated output only. 🔲 M2 (defaults in FR-4.6)
- **FR-S3 SSRF/URL fetch:** block private/link-local except explicitly-local providers; timeouts + size caps. 🔲 M2
- **FR-S4 Files:** never execute content; sanitised generated names; size/page/zip limits. 🔲 M2
- **FR-S5 Secrets:** never log secrets, secret-bearing prompts, or full text at info level. ✅ Done (M1; extend in M2)
- **FR-S6 RBAC:** admins manage credentials/providers/triggers/settings; project keys submit + read own jobs only. ◐ (M1 endpoints ✅; key-scoped extract rights in M2)

### B10. Local setup and non-functional notes

- Target dev machine: Windows 11, i5-9400F, 16 GB RAM, GTX 1660 (4 GB VRAM), repo on HDD.
- Ollama Modelfile (`actionbridge-qwen25-3b`): `FROM qwen2.5:3b`, `num_ctx 8192`, `temperature 0`; raise `num_ctx` only after VRAM checks. Status: 🔲 environment prerequisite (not started).
- Qwen2.5 3B is text-only; scans need vision cloud provider this iteration (or manual entry when disallowed).
- Concurrency: one local GPU job at a time; CPU pool for parsing/rendering/download.
- SQLite-on-HDD: keep DB file on SSD with WAL, configurable file-store root, batched worker commits. (Dev already runs WAL.)
- Queue: DB-backed; PG `FOR UPDATE SKIP LOCKED` semantics via atomic `UPDATE…RETURNING` claim (works on both engines); single worker process on SQLite; `python -m app.worker`, also wired into `dev.ps1`.
- Logging: structured logs with job/submission ids; counters (jobs by status, latency per provider).

### B11. Milestones and acceptance

- **M1: Foundations** — credentials, providers, processing, jobs + worker. ✅ **Done.** Accepted: Ollama + cloud provider addable/testable via API; secrets never in responses (33 tests, live-verified).
- **M2: Extraction pipeline** — profiles, text acquisition, validation/retry, grounding, hand-off, upload, `/extract` + idempotency + webhook, file viewer, M1 UI batch (providers/credentials/processing/jobs pages). 🔲 Accepted when: UI + API invoice upload → `pending_review` doc, schema-valid JSON, signals in confidence display, viewable source; same idempotency key ⇒ no duplicate.
- **M3: Email triggers** — IMAP + Gmail API + Graph connectors, OAuth lifecycle, wizard, filters, dry run, history, dedupe, skipped panel, combined mode. 🔲 Accepted when: invoice+GRN email (combined) → one two-section doc; invoice+junk (per-attachment) → one doc + one skipped; reprocessing same email ⇒ nothing new.
- **M4: Hardening** — jobs polish, scanned path via cloud vision, local-only enforcement proof, injection/SSRF tests, docs. 🔲 Accepted when: `allow_cloud = false` scans ⇒ `needs manual entry` with **zero** non-local calls in `provider_calls`.

### B12. Open items (owner)

1. ~~Mailbox types~~ — decided (A1: OAuth-first + IMAP fallback).
2. Scan handling when cloud disallowed — spec default stands (manual entry; local OCR later).
3. **Numeric grounding→confidence mapping** (FR-8.2 defaults are placeholders — tune or confirm).
4. **Retention period** for email bodies and attachments.
5. Google Cloud + Azure app registrations (owner one-time setup; guide below).

### Appendix — OAuth app setup guide (owner, ~15 min)

**Google Cloud (Gmail API):** create project → enable Gmail API (+ Drive API read-only if downloading Drive-linked files) → OAuth consent screen (Internal or External) → scopes `.../auth/gmail.readonly`, `.../auth/gmail.modify` (+ `.../auth/drive.readonly`) → Client ID (Web) with redirect `https://<host>/api/v1/credentials/oauth/gmail/callback` → paste client ID/secret when creating the `oauth2` credential in Action Bridge → complete the authorize flow in the UI.
**Azure (Microsoft Graph):** app registration → API permissions (delegated `Mail.ReadWrite`, `Files.Read`) → redirect URI `https://<host>/api/v1/credentials/oauth/graph/callback` → client secret → same credential flow in the UI. Admin consent may be required for organization-wide mailbox access.

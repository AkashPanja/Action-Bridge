from datetime import datetime

from pydantic import BaseModel, ConfigDict


# --- Credentials ---

class CredentialCreate(BaseModel):
    name: str
    type: str
    payload: dict  # meta + secrets; secrets are encrypted server-side


class CredentialSecretReplace(BaseModel):
    payload: dict


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    meta: dict = {}
    hint: str = ""


class CredentialTestResponse(BaseModel):
    ok: bool
    detail: str
    latency_ms: int | None = None
    parsed: bool | None = None


# --- Providers ---

class ProviderCreate(BaseModel):
    name: str
    kind: str
    base_url: str
    credential_id: str | None = None
    model: str
    vision: bool = False
    json_schema: bool = False
    json_object: bool = False
    max_concurrency: int = 1
    timeout_s: float = 120
    is_local: bool = False
    context_window: int | None = None
    enabled: bool = True
    extra_headers: dict = {}


class ProviderUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    credential_id: str | None = None
    model: str | None = None
    vision: bool | None = None
    json_schema: bool | None = None
    json_object: bool | None = None
    max_concurrency: int | None = None
    timeout_s: float | None = None
    is_local: bool | None = None
    context_window: int | None = None
    enabled: bool | None = None
    extra_headers: dict | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    base_url: str
    credential_id: str | None = None
    model: str
    vision: bool = False
    json_schema: bool = False
    json_object: bool = False
    max_concurrency: int = 1
    timeout_s: float = 120
    is_local: bool = False
    context_window: int | None = None
    enabled: bool = True
    extra_headers: dict = {}


class ProviderTestResponse(BaseModel):
    ok: bool
    detail: str
    latency_ms: int = 0
    json_mode: str | None = None
    json_ok: bool | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class ProviderModelsResponse(BaseModel):
    supported: bool
    models: list[str] = []
    detail: str = ""


# --- Processing settings ---

class ProcessingUpdate(BaseModel):
    cpu_workers: int | None = None
    max_jobs_in_flight: int | None = None
    default_retries: int | None = None
    default_timeout_s: int | None = None
    paused: bool | None = None
    auto_approve_threshold: float | None = None


# --- Jobs ---
class JobEnqueue(BaseModel):
    kind: str
    payload: dict = {}
    project_id: str | None = None
    provider_id: str | None = None
    max_attempts: int = 3


class JobFileSummary(BaseModel):
    filename: str
    status: str
    skip_reason: str | None = None
    document_id: str | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    submission_id: str | None = None
    kind: str
    status: str
    attempts: int
    error: str | None = None
    provider_id: str | None = None
    payload: dict = {}
    result: dict | None = None
    usage: dict | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None
    files: list[JobFileSummary] = []


class JobListResponse(BaseModel):
    total: int
    jobs: list[JobResponse]


# --- Profiles ---

class CandidateType(BaseModel):
    document_type_id: str
    name: str = ""
    ignore: bool = False


class ProfilePrompts(BaseModel):
    system: str | None = None
    extraction: str | None = None
    classification: str | None = None


class ProfileCreate(BaseModel):
    name: str
    mode: str = "per_attachment"
    candidate_types: list[CandidateType] = []
    target_document_type_id: str | None = None
    prompts: ProfilePrompts = ProfilePrompts()
    provider_chain: list[str] = []
    ocr_provider_id: str | None = None
    allow_cloud: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = None
    mode: str | None = None
    candidate_types: list[CandidateType] | None = None
    target_document_type_id: str | None = None
    prompts: ProfilePrompts | None = None
    provider_chain: list[str] | None = None
    ocr_provider_id: str | None = None
    allow_cloud: bool | None = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    mode: str
    candidate_types: list = []
    target_document_type_id: str | None = None
    prompts: dict = {}
    provider_chain: list = []
    ocr_provider_id: str | None = None
    allow_cloud: bool = False
    version: int = 1


class PlaygroundResponse(BaseModel):
    data: dict | None = None
    errors: list[str] = []
    classification: str | None = None
    provider: str | None = None
    model: str | None = None
    latency_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None


# --- Extract ---

class ExtractFile(BaseModel):
    filename: str
    content_base64: str


class ExtractRequest(BaseModel):
    profile_id: str | None = None
    document_type_id: str | None = None
    files: list[ExtractFile] = []
    urls: list[str] = []
    idempotency_key: str | None = None
    callback_url: str | None = None
    wait_seconds: int = 0
    metadata: dict = {}
    note: str | None = None


class ExtractAccepted(BaseModel):
    job_id: str
    submission_id: str
    status: str


class ExtractCompleted(BaseModel):
    job_id: str
    status: str
    submission_id: str
    document_ids: list[str] = []
    review_urls: list[str] = []


# --- Submissions ---
class SubmissionFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    mime: str
    size: int
    status: str
    skip_reason: str | None = None
    detected_type: str | None = None
    document_id: str | None = None


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source: str
    profile_id: str | None = None
    email_meta: dict | None = None
    idempotency_key: str | None = None
    note: str | None = None
    files: list[SubmissionFileResponse] = []


# --- Email triggers ---

class TriggerFilters(BaseModel):
    sender: str = ""
    subject_pattern: str = ""
    body_pattern: str = ""
    must_have_attachment: bool = True
    allowed_types: list[str] = []
    max_attachment_mb: float | None = None
    received_after: str | None = None


class TriggerAfterAction(BaseModel):
    mark_read: bool = True
    move_to_folder: str | None = None


class TriggerConfig(BaseModel):
    folder: str = "INBOX"
    poll_interval_s: int = 300
    filters: TriggerFilters = TriggerFilters()
    after_action: TriggerAfterAction = TriggerAfterAction()
    import_window: str = "7d"


class TriggerCreate(BaseModel):
    name: str
    credential_id: str | None = None
    profile_id: str | None = None
    mode_override: str | None = None
    config: TriggerConfig = TriggerConfig()
    enabled: bool = True


class TriggerUpdate(BaseModel):
    name: str | None = None
    credential_id: str | None = None
    profile_id: str | None = None
    mode_override: str | None = None
    config: TriggerConfig | None = None
    enabled: bool | None = None


class TriggerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    type: str = "email"
    credential_id: str | None = None
    profile_id: str | None = None
    mode_override: str | None = None
    config: dict = {}
    enabled: bool = True
    state: dict = {}


class TriggerRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trigger_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    seen: int = 0
    matched: int = 0
    submissions_created: int = 0
    jobs_enqueued: int = 0
    error: str | None = None
    dry_run: bool = False


class TriggerDryRunResponse(BaseModel):
    seen: int = 0
    matched: int = 0
    submissions_created: int = 0
    jobs_enqueued: int = 0
    matches: list[dict] = []
    error: str | None = None

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


class ProviderTestResponse(BaseModel):
    ok: bool
    detail: str
    latency_ms: int = 0
    json_mode: str | None = None
    json_ok: bool | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


# --- Processing settings ---

class ProcessingUpdate(BaseModel):
    cpu_workers: int | None = None
    max_jobs_in_flight: int | None = None
    default_retries: int | None = None
    default_timeout_s: int | None = None
    paused: bool | None = None


# --- Jobs ---

class JobEnqueue(BaseModel):
    kind: str
    payload: dict = {}
    project_id: str | None = None
    provider_id: str | None = None
    max_attempts: int = 3


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    kind: str
    status: str
    attempts: int
    error: str | None = None
    provider_id: str | None = None
    payload: dict = {}
    result: dict | None = None
    usage: dict | None = None


class JobListResponse(BaseModel):
    total: int
    jobs: list[JobResponse]

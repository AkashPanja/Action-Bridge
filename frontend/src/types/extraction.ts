export interface Credential {
  id: string;
  name: string;
  type: "api_key" | "basic" | "oauth2";
  meta: Record<string, unknown>;
  hint: string;
}

export interface Provider {
  id: string;
  name: string;
  kind: "openai_compatible" | "anthropic";
  base_url: string;
  credential_id: string | null;
  model: string;
  vision: boolean;
  json_schema: boolean;
  json_object: boolean;
  max_concurrency: number;
  timeout_s: number;
  is_local: boolean;
  context_window: number | null;
  enabled: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  detail: string;
  latency_ms: number;
  json_mode?: string | null;
  json_ok?: boolean | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
}

export interface ProcessingSettings {
  cpu_workers: number;
  max_jobs_in_flight: number;
  default_retries: number;
  default_timeout_s: number;
  paused: boolean;
}

export interface CandidateType {
  document_type_id: string;
  name?: string;
  ignore?: boolean;
}

export interface ExtractionProfile {
  id: string;
  project_id: string;
  name: string;
  mode: "per_attachment" | "combined";
  candidate_types: CandidateType[];
  target_document_type_id: string | null;
  prompts: Record<string, string>;
  provider_chain: string[];
  ocr_provider_id: string | null;
  allow_cloud: boolean;
  version: number;
}

export interface PlaygroundResult {
  data: Record<string, unknown> | null;
  errors: string[];
  classification?: string | null;
  provider?: string | null;
  model?: string | null;
  latency_ms: number;
  tokens_in?: number | null;
  tokens_out?: number | null;
}

export interface Job {
  id: string;
  project_id: string | null;
  kind: string;
  status: string;
  attempts: number;
  error: string | null;
  provider_id: string | null;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  usage: Record<string, unknown> | null;
}

export interface SubmissionFile {
  id: string;
  filename: string;
  mime: string;
  size: number;
  status: string;
  skip_reason: string | null;
  detected_type: string | null;
  document_id: string | null;
}

export interface Submission {
  id: string;
  project_id: string;
  source: string;
  profile_id: string | null;
  email_meta: Record<string, unknown> | null;
  idempotency_key: string | null;
  note: string | null;
  files: SubmissionFile[];
}

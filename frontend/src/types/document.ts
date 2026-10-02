export interface AuditEvent {
  id: string;
  document_id: string;
  action: string;
  actor: string;
  field_name: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  comment: string | null;
  timestamp: string;
}

export interface Document {
  id: string;
  project_id: string;
  document_type_id: string;
  status: string;
  extracted_data: Record<string, unknown>;
  confidence_score: number | null;
  confidence_scores?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  history?: AuditEvent[] | null;
  document_type_name?: string | null;
  submission_id?: string | null;
  source?: string | null;
  extraction_meta?: Record<string, unknown> | null;
}

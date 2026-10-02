import { motion } from "framer-motion";
import { ArrowLeft, CheckCircle2, History, Link, MessageSquare, Paperclip, Plus, ScanSearch, Send, Trash2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Skeleton } from "../../components/ui/Skeleton";
import { AnimatedPage } from "../../components/shared/AnimatedPage";
import { SourceFilesPanel } from "../../components/extraction/SourceFilesPanel";
import { useAuth } from "../../contexts/AuthContext";
import { useDocument, useUpdateDocument } from "../../hooks/useDocuments";
import { useDocumentType } from "../../hooks/useDocumentTypes";
import { formatDate } from "../../lib/utils";
import type { AuditEvent } from "../../types";

const API_BASE = "/api/v1";

const statusColors: Record<string, string> = {
  received: "bg-surface-100 text-surface-700 dark:bg-surface-700 dark:text-surface-300",
  pending_review: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  rejected: "bg-accent-100 text-accent-700 dark:bg-accent-900/30 dark:text-accent-300",
};

interface Comment {
  id: string;
  document_id: string;
  user_id: string;
  parent_id: string | null;
  content: string;
  created_at: string;
  updated_at: string;
  author_name: string;
  replies: Comment[];
}

interface Attachment {
  id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  url: string;
  created_at: string;
}

function confidenceColor(score: number | undefined): string {
  if (score == null) return "border-surface-200 dark:border-surface-600";
  if (score >= 0.85) return "border-emerald-400 dark:border-emerald-600";
  if (score >= 0.70) return "border-amber-400 dark:border-amber-600";
  return "border-accent-400 dark:border-accent-600";
}

function confidenceBadge(score: number | undefined) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  const color = score >= 0.85 ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
    : score >= 0.70 ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
    : "bg-accent-100 text-accent-700 dark:bg-accent-900/30 dark:text-accent-300";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${color}`} title={`Confidence: ${pct}%`}>
      {pct}%
    </span>
  );
}

function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <div className="relative space-y-0">
      {events.map((event, i) => {
        const isLast = i === events.length - 1;
        return (
          <div key={event.id} className="relative flex gap-4 pb-6">
            {!isLast ? (
              <div className="absolute left-[11px] top-5 h-full w-px bg-surface-200 dark:bg-surface-600" />
            ) : null}
            <div className="relative z-10 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-brand-200 bg-white dark:border-brand-800 dark:bg-surface-800">
              <div className="h-2 w-2 rounded-full bg-brand-500" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-surface-900 dark:text-surface-100">
                  {event.action.replace(/_/g, " ")}
                </span>
                <span className="text-xs text-surface-400">{formatDate(event.timestamp)}</span>
              </div>
              <p className="text-xs text-surface-500 dark:text-surface-400">by {event.actor}</p>
              {event.field_name ? (
                <p className="mt-1 text-xs text-surface-600 dark:text-surface-300">Field: {event.field_name}</p>
              ) : null}
              {event.comment ? (
                <p className="mt-0.5 rounded-lg bg-surface-100 px-3 py-1.5 text-xs text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                  "{event.comment}"
                </p>
              ) : null}
              {event.old_value && event.new_value ? (
                <div className="mt-1 flex gap-2 text-xs">
                  <span className="rounded bg-accent-50 px-1.5 py-0.5 text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">
                    {JSON.stringify(event.old_value)}
                  </span>
                  <span className="text-surface-400">→</span>
                  <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400">
                    {JSON.stringify(event.new_value)}
                  </span>
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CommentsSection({ projectId, documentId }: { projectId: string; documentId: string }) {
  const { token, user } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [newComment, setNewComment] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [loading, setLoading] = useState(true);

  async function fetchComments() {
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}/documents/${documentId}/comments`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setComments(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  }

  useEffect(() => { fetchComments(); }, [projectId, documentId]);

  async function addComment() {
    if (!newComment.trim()) return;
    await fetch(`${API_BASE}/projects/${projectId}/documents/${documentId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ content: newComment }),
    });
    setNewComment("");
    fetchComments();
  }

  async function addReply(parentId: string) {
    if (!replyText.trim()) return;
    await fetch(`${API_BASE}/projects/${projectId}/documents/${documentId}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ content: replyText, parent_id: parentId }),
    });
    setReplyText("");
    setReplyTo(null);
    fetchComments();
  }

  async function deleteComment(commentId: string) {
    await fetch(`${API_BASE}/projects/${projectId}/documents/${documentId}/comments/${commentId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchComments();
  }

  if (loading) return <Skeleton className="h-32 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-4 w-4 text-surface-400" />
        <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Comments</h3>
      </div>

      <div className="flex gap-2">
        <input
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          onKeyDown={(e) => e.key === "Enter" && addComment()}
          className="flex-1 rounded-lg border border-surface-300 bg-white px-3 py-2 text-sm focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
        />
        <Button size="sm" onClick={addComment} disabled={!newComment.trim()}>
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="space-y-3">
        {comments.length === 0 && <p className="text-sm text-surface-400">No comments yet.</p>}
        {comments.map((c) => (
          <div key={c.id}>
            <div className="rounded-lg bg-surface-50 p-3 dark:bg-surface-800">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-surface-700 dark:text-surface-300">{c.author_name}</span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setReplyTo(replyTo === c.id ? null : c.id)} className="text-[10px] text-accent-500 hover:text-accent-600">
                    Reply
                  </button>
                  {(c.user_id === user?.id) && (
                    <button onClick={() => deleteComment(c.id)} className="text-[10px] text-accent-400 hover:text-accent-600">
                      Delete
                    </button>
                  )}
                </div>
              </div>
              <p className="mt-1 text-sm text-surface-600 dark:text-surface-300">{c.content}</p>
            </div>

            {replyTo === c.id && (
              <div className="ml-6 mt-2 flex gap-2">
                <input
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Write a reply..."
                  onKeyDown={(e) => e.key === "Enter" && addReply(c.id)}
                  className="flex-1 rounded-lg border border-surface-300 bg-white px-3 py-1.5 text-xs focus:border-accent-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                />
                <button onClick={() => addReply(c.id)} className="rounded-lg bg-accent-500 px-2 py-1.5 text-xs text-white hover:bg-accent-600">
                  Reply
                </button>
              </div>
            )}

            {c.replies?.map((r) => (
              <div key={r.id} className="ml-6 mt-2 rounded-lg bg-surface-50/50 p-3 dark:bg-surface-800/50">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-surface-600 dark:text-surface-400">{r.author_name}</span>
                  {(r.user_id === user?.id) && (
                    <button onClick={() => deleteComment(r.id)} className="text-[10px] text-accent-400 hover:text-accent-600">
                      Delete
                    </button>
                  )}
                </div>
                <p className="mt-1 text-sm text-surface-600 dark:text-surface-300">{r.content}</p>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function AttachmentsSection({ projectId, documentId }: { projectId: string; documentId: string }) {
  const { token } = useAuth();
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function fetchAttachments() {
    try {
      const res = await fetch(`${API_BASE}/attachments/${documentId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setAttachments(await res.json());
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchAttachments(); }, [documentId]);

  async function uploadFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await fetch(`${API_BASE}/attachments/${documentId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      fetchAttachments();
    } catch { /* ignore */ }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Paperclip className="h-4 w-4 text-surface-400" />
        <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Attachments</h3>
        <label className="ml-auto cursor-pointer rounded-lg bg-surface-100 px-3 py-1.5 text-xs font-medium text-surface-600 transition-colors hover:bg-surface-200 dark:bg-surface-700 dark:text-surface-400 dark:hover:bg-surface-600">
          {uploading ? "Uploading..." : "Upload"}
          <input ref={fileRef} type="file" className="hidden" onChange={uploadFile} />
        </label>
      </div>
      {attachments.length === 0 ? (
        <p className="text-sm text-surface-400">No attachments.</p>
      ) : (
        <div className="space-y-1.5">
          {attachments.map((a) => (
            <div key={a.id} className="flex items-center gap-2 rounded-lg bg-surface-50 px-3 py-2 dark:bg-surface-800">
              <Paperclip className="h-3.5 w-3.5 shrink-0 text-surface-400" />
              <a href={a.url} target="_blank" rel="noopener noreferrer" className="flex-1 truncate text-sm text-accent-600 hover:text-accent-700 underline dark:text-accent-400 dark:hover:text-accent-300">{a.file_name}</a>
              <span className="shrink-0 text-[10px] text-surface-400">{formatSize(a.file_size)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function DocumentDetail() {
  const { projectId, docId } = useParams<{ projectId: string; docId: string }>();
  const navigate = useNavigate();
  const { data: doc, isLoading } = useDocument(projectId!, docId!, true);
  const { data: docType } = useDocumentType(projectId!, doc?.document_type_id ?? "");
  const updateDoc = useUpdateDocument(projectId!);

  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [comment, setComment] = useState("");
  const [hasChanges, setHasChanges] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (docType?.schema_definition && Object.keys(formData).length === 0) {
      const schema = docType.schema_definition as { properties?: Record<string, unknown> };
      const existing = (doc?.extracted_data as Record<string, unknown>) ?? {};
      const merged: Record<string, unknown> = {};
      for (const key of Object.keys(schema.properties ?? {})) {
        merged[key] = key in existing ? existing[key] : "";
      }
      setFormData(merged);
    }
  }, [doc, docType]);

  function inferFieldType(key: string): string {
    const prop = (docType?.schema_definition as { properties?: Record<string, unknown> })?.properties?.[key] as Record<string, unknown> | undefined;
    return (prop?.type as string) ?? "string";
  }

  function coerceValue(key: string, rawValue: string): unknown {
    const t = inferFieldType(key);
    if (t === "number") return rawValue === "" ? "" : parseFloat(rawValue);
    if (t === "boolean") return rawValue === "true" ? true : rawValue === "false" ? false : rawValue;
    return rawValue;
  }

  function handleFieldChange(key: string, rawValue: string) {
    const value = coerceValue(key, rawValue);
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
    setSaveError("");
  }

  function handleTableCellChange(key: string, rowIndex: number, colKey: string, rawValue: string) {
    const items = ((docType?.schema_definition as { properties?: Record<string, unknown> })?.properties?.[key] as Record<string, unknown> | undefined)?.items as Record<string, unknown> | undefined;
    const colProp = (items?.properties as Record<string, unknown> | undefined)?.[colKey] as Record<string, unknown> | undefined;
    const colType = (colProp?.type as string) ?? "string";
    let value: unknown = rawValue;
    if (colType === "number") value = rawValue === "" ? "" : parseFloat(rawValue);
    else if (colType === "boolean") value = rawValue === "true" ? true : rawValue === "false" ? false : rawValue;
    setFormData((prev) => {
      const rows = [...((prev[key] as unknown[]) ?? [])];
      rows[rowIndex] = { ...(rows[rowIndex] as Record<string, unknown>), [colKey]: value };
      return { ...prev, [key]: rows };
    });
    setHasChanges(true);
    setSaveError("");
  }

  function addTableRow(key: string) {
    setFormData((prev) => {
      const rows = [...((prev[key] as unknown[]) ?? [])];
      const prop = (docType?.schema_definition as { properties?: Record<string, unknown> })?.properties?.[key] as Record<string, unknown> | undefined;
      const items = prop?.items as Record<string, unknown> | undefined;
      const itemProps = (items?.properties as Record<string, unknown>) ?? {};
      const newRow: Record<string, unknown> = {};
      for (const colKey of Object.keys(itemProps)) {
        newRow[colKey] = "";
      }
      rows.push(newRow);
      return { ...prev, [key]: rows };
    });
    setHasChanges(true);
    setSaveError("");
  }

  function removeTableRow(key: string, rowIndex: number) {
    setFormData((prev) => {
      const rows = [...((prev[key] as unknown[]) ?? [])];
      rows.splice(rowIndex, 1);
      return { ...prev, [key]: rows };
    });
    setHasChanges(true);
    setSaveError("");
  }

  async function handleSave() {
    if (!doc) return;
    setSaveError("");
    try {
      await updateDoc.mutateAsync({ docId: doc.id, data: { extracted_data: formData, comment: comment || undefined } });
      setHasChanges(false);
      setComment("");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save");
    }
  }

  async function handleApprove() {
    if (!doc) return;
    setSaveError("");
    try {
      await updateDoc.mutateAsync({ docId: doc.id, data: { status: "approved", comment: comment || undefined } });
      setComment("");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to approve");
    }
  }

  async function handleReject() {
    if (!doc) return;
    setSaveError("");
    try {
      await updateDoc.mutateAsync({ docId: doc.id, data: { status: "rejected", comment: comment || undefined } });
      setComment("");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to reject");
    }
  }

  if (isLoading) {
    return (
      <AnimatedPage>
        <Skeleton className="mb-4 h-8 w-48" />
        <Skeleton className="h-96 w-full" />
      </AnimatedPage>
    );
  }

  if (!doc) {
    return (
      <AnimatedPage>
        <p className="text-surface-500">Document not found.</p>
      </AnimatedPage>
    );
  }

  const schema = docType?.schema_definition as { properties?: Record<string, unknown>; required?: string[] } | undefined;
  const schemaProperties = schema?.properties ?? {};
  const required = schema?.required ?? [];
  const confidenceScores = (doc.confidence_scores ?? {}) as Record<string, unknown>;
  const canEdit = doc.status === "pending_review" || doc.status === "received";

  return (
    <AnimatedPage>
      <button
        onClick={() => navigate(`/projects/${projectId}?tab=documents`)}
        className="mb-4 flex items-center gap-1.5 text-sm text-surface-500 transition-colors hover:text-surface-700 dark:hover:text-surface-300"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to documents
      </button>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-bold text-surface-900 dark:text-surface-100">
              {doc.document_type_name ?? "Document"}
            </h1>
            <span className={`rounded-full px-3 py-0.5 text-xs font-medium ${statusColors[doc.status] ?? ""}`}>
              {doc.status.replace(/_/g, " ")}
            </span>
            {doc.source ? (
              <span className="rounded-full bg-brand-100 px-3 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
                via {doc.source}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm text-surface-500">
            Created {formatDate(doc.created_at)}
            {doc.confidence_score != null ? ` · Avg confidence: ${Math.round(doc.confidence_score * 100)}%` : ""}
          </p>
        </div>
        {canEdit ? (
          <div className="flex items-center gap-2">
            <Button variant="danger" size="sm" onClick={handleReject} isLoading={updateDoc.isPending}>
              <XCircle className="h-4 w-4" /> Reject
            </Button>
            <Button variant="primary" size="sm" onClick={handleApprove} isLoading={updateDoc.isPending}>
              <CheckCircle2 className="h-4 w-4" /> Approve
            </Button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Card className="space-y-4">
            <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Extracted Data</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(formData).map(([key, value]) => {
                const prop = schemaProperties[key] as Record<string, unknown> | undefined;
                const propType = prop?.type as string | undefined;
                const propTitle = prop?.title as string | undefined;
                const propEnum = prop?.enum as string[] | undefined;
                const propFormat = prop?.format as string | undefined;
                const isRequired = required.includes(key);
                const score = confidenceScores[key];

                const borderClass = typeof score === "number" ? confidenceColor(score) : "border-surface-200 dark:border-surface-600";
                const label = (
                  <span className="flex items-center gap-1.5">
                    {propTitle ?? key}
                    {isRequired ? <span className="text-accent-500">*</span> : null}
                    {typeof score === "number" ? confidenceBadge(score) : null}
                  </span>
                );

                if (propEnum) {
                  return (
                    <div key={key} className="space-y-1.5">
                      <label className="text-sm font-medium text-surface-700 dark:text-surface-300">{label}</label>
                      <select
                        value={String(value ?? "")}
                        onChange={(e) => handleFieldChange(key, e.target.value)}
                        disabled={!canEdit}
                        className={`w-full rounded-xl border-2 bg-white px-4 py-2.5 text-sm text-surface-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${borderClass}`}
                      >
                        <option value="">Select...</option>
                        {propEnum.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </div>
                  );
                }

                if (propFormat === "date") {
                  return (
                    <div key={key} className="space-y-1.5">
                      <label className="text-sm font-medium text-surface-700 dark:text-surface-300">{label}</label>
                      <input
                        type="date"
                        value={String(value ?? "")}
                        onChange={(e) => handleFieldChange(key, e.target.value)}
                        disabled={!canEdit}
                        className={`w-full rounded-xl border-2 bg-white px-4 py-2.5 text-sm text-surface-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${borderClass}`}
                      />
                    </div>
                  );
                }

                if (propType === "number") {
                  return (
                    <div key={key} className="space-y-1.5">
                      <label className="text-sm font-medium text-surface-700 dark:text-surface-300">{label}</label>
                      <input
                        type="number"
                        step="any"
                        value={String(value ?? "")}
                        onChange={(e) => handleFieldChange(key, e.target.value)}
                        disabled={!canEdit}
                        className={`w-full rounded-xl border-2 bg-white px-4 py-2.5 text-sm text-surface-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${borderClass}`}
                      />
                    </div>
                  );
                }

                if (propType === "boolean") {
                  return (
                    <div key={key} className="space-y-1.5">
                      <label className="text-sm font-medium text-surface-700 dark:text-surface-300">{label}</label>
                      <select
                        value={String(value ?? "")}
                        onChange={(e) => handleFieldChange(key, e.target.value)}
                        disabled={!canEdit}
                        className={`w-full rounded-xl border-2 bg-white px-4 py-2.5 text-sm text-surface-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${borderClass}`}
                      >
                        <option value="">Select...</option>
                        <option value="true">True</option>
                        <option value="false">False</option>
                      </select>
                    </div>
                  );
                }

                if (propType === "array") {
                  const items = prop?.items as Record<string, unknown> | undefined;
                  const itemProps = (items?.properties as Record<string, unknown>) ?? {};
                  const rows = (value as Array<Record<string, unknown>>) ?? [];
                  const rowScores = (score as Array<Record<string, number>> | undefined) ?? [];
                  const itemRequired = (items?.required as string[]) ?? [];
                  return (
                    <div key={key} className="col-span-2 space-y-2">
                      <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
                        <span className="flex items-center gap-1.5">
                          {propTitle ?? key}
                          {isRequired ? <span className="text-accent-500">*</span> : null}
                        </span>
                      </label>
                      <div className="overflow-x-auto rounded-xl border border-surface-200 dark:border-surface-600">
                        <table className="w-full min-w-[560px] text-sm">
                          <thead>
                            <tr className="bg-surface-50 dark:bg-surface-800">
                              {Object.entries(itemProps).map(([colKey, colVal]) => {
                                const colProp = colVal as Record<string, unknown>;
                                return (
                                  <th key={colKey} className="px-3 py-2 text-left text-xs font-medium text-surface-500">
                                    {colProp.title as string ?? colKey}
                                    {itemRequired.includes(colKey) ? <span className="ml-0.5 text-accent-500">*</span> : null}
                                  </th>
                                );
                              })}
                              <th className="w-10 px-2 py-2"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((row, ri) => (
                              <tr key={ri} className="border-t border-surface-100 dark:border-surface-700">
                                {Object.entries(itemProps).map(([colKey, colVal]) => {
                                  const colProp = colVal as Record<string, unknown>;
                                  const colType = (colProp.type as string) ?? "string";
                                  const colFormat = colProp.format as string;
                                  const colEnum = colProp.enum as string[] | undefined;
                                  const cellScore = rowScores[ri]?.[colKey];
                                  const cellBorder = confidenceColor(cellScore);
                                  return (
                                    <td key={colKey} className="px-3 py-1.5">
                                      {colEnum ? (
                                        <select
                                          value={String(row[colKey] ?? "")}
                                          onChange={(e) => handleTableCellChange(key, ri, colKey, e.target.value)}
                                          disabled={!canEdit}
                                          className={`w-full rounded-lg border-2 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${cellBorder}`}
                                        >
                                          <option value="">Select...</option>
                                          {colEnum.map((opt) => (
                                            <option key={opt} value={opt}>{opt}</option>
                                          ))}
                                        </select>
                                      ) : colFormat === "date" ? (
                                        <input
                                          type="date"
                                          value={String(row[colKey] ?? "")}
                                          onChange={(e) => handleTableCellChange(key, ri, colKey, e.target.value)}
                                          disabled={!canEdit}
                                          className={`w-full rounded-lg border-2 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${cellBorder}`}
                                        />
                                      ) : colType === "number" ? (
                                        <input
                                          type="number"
                                          step="any"
                                          value={String(row[colKey] ?? "")}
                                          onChange={(e) => handleTableCellChange(key, ri, colKey, e.target.value)}
                                          disabled={!canEdit}
                                          className={`w-full rounded-lg border-2 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${cellBorder}`}
                                        />
                                      ) : colType === "boolean" ? (
                                        <select
                                          value={String(row[colKey] ?? "")}
                                          onChange={(e) => handleTableCellChange(key, ri, colKey, e.target.value)}
                                          disabled={!canEdit}
                                          className={`w-full rounded-lg border-2 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${cellBorder}`}
                                        >
                                          <option value="">Select...</option>
                                          <option value="true">True</option>
                                          <option value="false">False</option>
                                        </select>
                                      ) : (
                                        <input
                                          type="text"
                                          value={String(row[colKey] ?? "")}
                                          onChange={(e) => handleTableCellChange(key, ri, colKey, e.target.value)}
                                          disabled={!canEdit}
                                          className={`w-full rounded-lg border-2 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${cellBorder}`}
                                        />
                                      )}
                                      {confidenceBadge(cellScore)}
                                    </td>
                                  );
                                })}
                                <td className="px-2 py-1.5 text-center">
                                  {canEdit && rows.length > 1 ? (
                                    <button
                                      type="button"
                                      onClick={() => removeTableRow(key, ri)}
                                      className="rounded p-1 text-accent-400 hover:bg-accent-50 hover:text-accent-600 dark:hover:bg-accent-900/20"
                                    >
                                      <XCircle className="h-3.5 w-3.5" />
                                    </button>
                                  ) : null}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {canEdit ? (
                        <button
                          type="button"
                          onClick={() => addTableRow(key)}
                          className="flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
                        >
                          <Plus className="h-3.5 w-3.5" /> Add Row
                        </button>
                      ) : null}
                    </div>
                  );
                }

                return (
                  <div key={key} className="space-y-1.5">
                    <label className="text-sm font-medium text-surface-700 dark:text-surface-300">{label}</label>
                    <input
                      type="text"
                      value={String(value ?? "")}
                      onChange={(e) => handleFieldChange(key, e.target.value)}
                      disabled={!canEdit}
                      className={`w-full rounded-xl border-2 bg-white px-4 py-2.5 text-sm text-surface-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-50 dark:bg-surface-800 dark:text-surface-100 ${borderClass}`}
                    />
                  </div>
                );
              })}
            </div>

            {canEdit ? (
              <div className="space-y-3 pt-2">
                <Input
                  label="Comment (optional)"
                  placeholder="Add a note about this change..."
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  id="comment"
                />
                {saveError ? (
                  <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{saveError}</motion.p>
                ) : null}
                <div className="flex gap-2">
                  <Button onClick={handleSave} isLoading={updateDoc.isPending} disabled={!hasChanges && !comment}>
                    Save Changes
                  </Button>
                  {hasChanges ? (
                    <Button variant="ghost" onClick={() => {
                      const schema = docType?.schema_definition as { properties?: Record<string, unknown> } | undefined;
                      const existing = (doc?.extracted_data as Record<string, unknown>) ?? {};
                      const merged: Record<string, unknown> = {};
                      for (const key of Object.keys(schema?.properties ?? {})) {
                        merged[key] = key in existing ? existing[key] : "";
                      }
                      setFormData(merged);
                      setHasChanges(false);
                      setSaveError("");
                    }}>
                      Reset
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </Card>

          <Card>
            <CommentsSection projectId={projectId!} documentId={docId!} />
          </Card>
        </div>

        <div className="lg:col-span-1 space-y-4">
          {doc.source || doc.submission_id ? (
            <Card>
              <div className="mb-4 flex items-center gap-2">
                <ScanSearch className="h-4 w-4 text-surface-400" />
                <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Extraction Source</h2>
              </div>
              {doc.extraction_meta ? (
                <dl className="mb-3 space-y-1 text-xs">
                  {(
                    [
                      ["Provider", doc.extraction_meta.provider],
                      ["Model", doc.extraction_meta.model],
                      ["Tokens in/out", doc.extraction_meta.tokens_in != null || doc.extraction_meta.tokens_out != null
                        ? `${doc.extraction_meta.tokens_in ?? "?"} / ${doc.extraction_meta.tokens_out ?? "?"}`
                        : null],
                      ["Latency", doc.extraction_meta.latency_ms != null ? `${doc.extraction_meta.latency_ms} ms` : null],
                      ["Prompt", doc.extraction_meta.prompt_version != null ? `v${doc.extraction_meta.prompt_version}` : null],
                    ] as [string, unknown][]
                  ).filter(([, v]) => v != null && v !== "").map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-2">
                      <dt className="text-surface-400">{k}</dt>
                      <dd className="truncate font-medium text-surface-700 dark:text-surface-200">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {doc.submission_id ? <SourceFilesPanel submissionId={doc.submission_id} /> : null}
            </Card>
          ) : null}
          <Card>
            <div className="mb-4 flex items-center gap-2">
              <History className="h-4 w-4 text-surface-400" />
              <h2 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Audit History</h2>
            </div>
            {doc.history && doc.history.length > 0 ? (
              <AuditTimeline events={doc.history} />
            ) : (
              <p className="py-8 text-center text-sm text-surface-400">No history yet</p>
            )}
          </Card>

          <Card>
            <AttachmentsSection projectId={projectId!} documentId={docId!} />
          </Card>
        </div>
      </div>
    </AnimatedPage>
  );
}

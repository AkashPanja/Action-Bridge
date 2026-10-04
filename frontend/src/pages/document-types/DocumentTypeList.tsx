import { motion } from "framer-motion";
import { Bell, Copy, FileType, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { can } from "../../lib/rbac";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { CardSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { useBulkDeleteDocumentTypes, useCloneDocumentType, useDeleteDocumentType, useDocumentTypes } from "../../hooks/useDocumentTypes";
import { formatDate } from "../../lib/utils";
import { ValidationRulesDialog } from "../../components/schema/ValidationRulesDialog";
import { DocumentTypeCreateDialog } from "./DocumentTypeCreate";
import { DocumentTypeEditDialog } from "./DocumentTypeEdit";

const API_BASE = "/api/v1";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" } },
};

interface Props {
  projectId?: string;
}

export function DocumentTypeList({ projectId: propProjectId }: Props) {
  const params = useParams<{ projectId: string }>();
  const projectId = propProjectId ?? params.projectId!;
  const { data: docTypes, isLoading } = useDocumentTypes(projectId);
  const { user, token } = useAuth();
  const deleteDocType = useDeleteDocumentType(projectId);
  const bulkDelete = useBulkDeleteDocumentTypes(projectId);
  const cloneDocType = useCloneDocumentType(projectId);
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingDocType, setEditingDocType] = useState<{ id: string; name: string; schema_definition: Record<string, unknown>; validation_rules?: Record<string, unknown> | null; confidence_threshold?: number | null } | null>(null);
  const [rulesDocType, setRulesDocType] = useState<{ id: string; name: string; schema_definition: Record<string, unknown>; validation_rules?: Record<string, unknown> | null; confidence_threshold?: number | null } | null>(null);
  const [subscriptions, setSubscriptions] = useState<Record<string, string[]>>({});
  const [subLoading, setSubLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    async function loadSubs() {
      try {
        const res = await fetch(`${API_BASE}/subscriptions`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          const map: Record<string, string[]> = {};
          data.forEach((s: { document_type_id: string; notify_on: string[] }) => {
            map[s.document_type_id] = s.notify_on;
          });
          setSubscriptions(map);
        }
      } catch { /* ignore */ }
    }
    loadSubs();
  }, [token]);

  async function toggleSubscription(docTypeId: string, event: React.MouseEvent) {
    event.stopPropagation();
    if (!token) return;
    const current = subscriptions[docTypeId] ?? [];
    const notifyOn = current.length > 0 ? [] : ["pending_review", "rejected"];
    try {
      await fetch(`${API_BASE}/subscriptions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ document_type_id: docTypeId, notify_on: notifyOn }),
      });
      setSubscriptions((prev) => ({ ...prev, [docTypeId]: notifyOn }));
    } catch { /* ignore */ }
  }

  const canWrite = user && can(user.role, "document_types:write");

  const fieldCount = (schema: Record<string, unknown>) => {
    const props = (schema as { properties?: Record<string, unknown> }).properties;
    return props ? Object.keys(props).length : 0;
  };

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleBulkDelete() {
    if (selected.size === 0) return;
    if (confirm(`Delete ${selected.size} document type${selected.size > 1 ? "s" : ""}?`)) {
      bulkDelete.mutate(Array.from(selected), {
        onSuccess: () => setSelected(new Set()),
      });
    }
  }

  return (
    <div>
      {canWrite ? (
        <div className="mb-4 flex justify-end">
          <button
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-brand-500/25 transition-all hover:bg-brand-600 hover:shadow-brand-500/40 active:scale-[0.98]"
          >
            <Plus className="h-4 w-4" />
            New Document Type
          </button>
        </div>
      ) : null}

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : docTypes && docTypes.length > 0 ? (
        <>
          <motion.div
            variants={container}
            initial="hidden"
            animate="show"
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          >
            {docTypes.map((dt) => (
              <motion.div key={dt.id} variants={item}>
                <Card className="group relative overflow-hidden">
                  <div className="mb-3 flex items-center gap-3">
                    {canWrite ? (
                      <input
                        type="checkbox"
                        checked={selected.has(dt.id)}
                        onChange={() => toggle(dt.id)}
                        className="h-4 w-4 shrink-0 rounded border-surface-300 text-brand-500 focus:ring-brand-500 dark:border-surface-600"
                      />
                    ) : null}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">
                      <FileType className="h-5 w-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="truncate text-sm font-semibold text-surface-900 dark:text-surface-100">
                        {dt.name}
                      </h3>
                      <p className="text-xs text-surface-400">
                        {fieldCount(dt.schema_definition)} fields
                        {dt.document_count != null ? ` · ${dt.document_count} document${dt.document_count !== 1 ? "s" : ""}` : ""}
                        {dt.confidence_threshold != null ? ` · auto-approve ≥ ${dt.confidence_threshold}` : ""}
                      </p>
                    </div>
                    <Badge variant="default">
                      {formatDate(dt.created_at).split(",")[0]}
                    </Badge>
                    {canWrite ? (
                      <>
                        <button
                          onClick={() => setEditingDocType({ id: dt.id, name: dt.name, schema_definition: dt.schema_definition, validation_rules: dt.validation_rules, confidence_threshold: dt.confidence_threshold })}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-surface-400 transition-all hover:bg-brand-50 hover:text-brand-500 dark:hover:bg-brand-900/20"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            const name = prompt("Name for cloned document type:", `${dt.name} (Copy)`);
                            if (name) cloneDocType.mutate({ typeId: dt.id, name });
                          }}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-surface-400 transition-all hover:bg-violet-50 hover:text-violet-500 dark:hover:bg-violet-900/20"
                          title="Clone"
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => setRulesDocType({ id: dt.id, name: dt.name, schema_definition: dt.schema_definition, validation_rules: dt.validation_rules, confidence_threshold: dt.confidence_threshold })}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-surface-400 transition-all hover:bg-emerald-50 hover:text-emerald-500 dark:hover:bg-emerald-900/20"
                        >
                          <ShieldCheck className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={(e) => toggleSubscription(dt.id, e)}
                          disabled={subLoading}
                          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-all ${
                            subscriptions[dt.id]?.length
                              ? "text-brand-500 hover:bg-brand-500 hover:bg-brand-50 hover:text-brand-600"
                              : "text-surface-400 hover:bg-amber-50 hover:text-amber-500"
                          }`}
                          title={subscriptions[dt.id]?.length ? "Unsubscribe from notifications" : "Subscribe to notifications"}
                        >
                          <Bell className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            if (confirm("Delete this document type?")) {
                              deleteDocType.mutate(dt.id);
                            }
                          }}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-surface-400 transition-all hover:bg-accent-50 hover:text-accent-500 dark:hover:bg-accent-900/20"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.keys(
                      (dt.schema_definition as { properties?: Record<string, unknown> }).properties ?? {},
                    ).slice(0, 4).map((key) => (
                      <span
                        key={key}
                        className="rounded-lg bg-surface-100 px-2 py-0.5 text-xs font-medium text-surface-600 dark:bg-surface-700 dark:text-surface-300"
                      >
                        {key.replace(/_/g, " ")}
                      </span>
                    ))}
                    {fieldCount(dt.schema_definition) > 4 ? (
                      <span className="rounded-lg bg-surface-100 px-2 py-0.5 text-xs font-medium text-surface-400 dark:bg-surface-700">
                        +{fieldCount(dt.schema_definition) - 4}
                      </span>
                    ) : null}
                  </div>
                </Card>
              </motion.div>
            ))}
          </motion.div>

          {canWrite && selected.size > 0 ? (
            <div className="fixed bottom-8 left-1/2 z-50 -translate-x-1/2">
              <div className="flex items-center gap-3 rounded-2xl border border-surface-300 bg-white px-5 py-3 shadow-xl dark:border-surface-600 dark:bg-surface-800">
                <span className="text-sm font-medium text-surface-700 dark:text-surface-200">
                  {selected.size} selected
                </span>
                <div className="h-5 w-px bg-surface-300 dark:bg-surface-600" />
                <button
                  onClick={handleBulkDelete}
                  disabled={bulkDelete.isPending}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-accent-500 px-3.5 py-1.5 text-sm font-medium text-white transition-all hover:bg-accent-600 active:scale-[0.97] disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {bulkDelete.isPending ? "Deleting..." : "Delete Selected"}
                </button>
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <EmptyState
          icon={<FileType className="h-8 w-8" />}
          title="No document types"
          description="Define your first document schema. Each document type has its own JSON schema and validation rules."
          action={(canWrite) ? {
            label: "Create Document Type",
            onClick: () => setCreateOpen(true),
          } : undefined}
        />
      )}

      <DocumentTypeCreateDialog
        projectId={projectId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      <DocumentTypeEditDialog
        key={editingDocType?.id ?? "none"}
        projectId={projectId}
        docType={editingDocType ? { id: editingDocType.id, name: editingDocType.name, schema_definition: editingDocType.schema_definition, validation_rules: editingDocType.validation_rules, confidence_threshold: editingDocType.confidence_threshold } : null}
        onClose={() => setEditingDocType(null)}
      />
      <ValidationRulesDialog
        key={`rules-${rulesDocType?.id ?? "none"}`}
        projectId={projectId}
        docType={rulesDocType}
        open={!!rulesDocType}
        onOpenChange={(open) => { if (!open) setRulesDocType(null); }}
      />
    </div>
  );
}

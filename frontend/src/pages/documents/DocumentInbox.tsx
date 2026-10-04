import { motion } from "framer-motion";
import { FileDown, FileText, Filter, Inbox, RotateCcw, Search, Trash2, UploadCloud } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { can } from "../../lib/rbac";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { CardSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { Input } from "../../components/ui/Input";
import { UploadModal } from "../../components/extraction/UploadModal";
import { useDocumentTypes } from "../../hooks/useDocumentTypes";
import { useBulkDeleteDocuments, useDocuments } from "../../hooks/useDocuments";
import { formatDate } from "../../lib/utils";

const statusConfig: Record<string, { label: string; variant: "warning" | "success" | "danger" | "default" }> = {
  received: { label: "Received", variant: "default" },
  pending_review: { label: "Pending Review", variant: "warning" },
  approved: { label: "Approved", variant: "success" },
  rejected: { label: "Rejected", variant: "danger" },
};

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04, delayChildren: 0.05 },
  },
};

const cardItem = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25, ease: "easeOut" } },
};

interface Props {
  projectId: string;
}

export function DocumentInbox({ projectId }: Props) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [confidenceMin, setConfidenceMin] = useState("");
  const [confidenceMax, setConfidenceMax] = useState("");
  const [sortBy, setSortBy] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploadOpen, setUploadOpen] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();

  const canWrite = user && can(user.role, "documents:write");

  const { data: docTypes } = useDocumentTypes(projectId);
  const { data: docs, isLoading } = useDocuments(projectId, {
    search: search || undefined,
    status: statusFilter || undefined,
    document_type_id: typeFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    confidence_min: confidenceMin ? parseFloat(confidenceMin) : undefined,
    confidence_max: confidenceMax ? parseFloat(confidenceMax) : undefined,
    sort_by: sortBy || undefined,
    sort_order: sortBy ? "desc" : undefined,
  });
  const bulkDelete = useBulkDeleteDocuments(projectId);

  function clearFilters() {
    setSearch("");
    setStatusFilter("");
    setTypeFilter("");
    setDateFrom("");
    setDateTo("");
    setConfidenceMin("");
    setConfidenceMax("");
    setSortBy("");
  }

  function getStatusBadge(status: string) {
    const config = statusConfig[status] ?? { label: status, variant: "default" as const };
    return <Badge variant={config.variant}>{config.label}</Badge>;
  }

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
    if (confirm(`Delete ${selected.size} document${selected.size > 1 ? "s" : ""}?`)) {
      bulkDelete.mutate(Array.from(selected), {
        onSuccess: () => setSelected(new Set()),
      });
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" />
          <Input
            placeholder="Search documents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Filter className="h-4 w-4 text-surface-400" />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        >
          <option value="">All statuses</option>
          <option value="pending_review">Pending Review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        >
          <option value="">All types</option>
          {docTypes?.map((dt) => (
            <option key={dt.id} value={dt.id}>
              {dt.name}
            </option>
          ))}
        </select>
        {canWrite ? (
          <Button size="sm" onClick={() => setUploadOpen(true)} className="ml-auto">
            <UploadCloud className="h-4 w-4" /> Upload
          </Button>
        ) : null}
      </div>
      <UploadModal projectId={projectId} open={uploadOpen} onClose={() => setUploadOpen(false)} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          title="From date"
          className="rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        />
        <span className="text-xs text-surface-400">to</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          title="To date"
          className="rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        />
        <div className="h-5 w-px bg-surface-300 dark:bg-surface-600" />
        <input
          type="number"
          value={confidenceMin}
          onChange={(e) => setConfidenceMin(e.target.value)}
          placeholder="Min conf."
          min="0"
          max="1"
          step="0.01"
          title="Minimum confidence"
          className="w-24 rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        />
        <span className="text-xs text-surface-400">to</span>
        <input
          type="number"
          value={confidenceMax}
          onChange={(e) => setConfidenceMax(e.target.value)}
          placeholder="Max conf."
          min="0"
          max="1"
          step="0.01"
          title="Maximum confidence"
          className="w-24 rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        />
        <div className="h-5 w-px bg-surface-300 dark:bg-surface-600" />
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm text-surface-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-200"
        >
          <option value="">Newest first</option>
          <option value="confidence_score">Confidence (high first)</option>
          <option value="updated_at">Recently updated</option>
        </select>
        <div className="h-5 w-px bg-surface-300 dark:bg-surface-600" />
        <button
          onClick={() => {
            const params = new URLSearchParams({ format: "csv" });
            if (statusFilter) params.set("status", statusFilter);
            if (typeFilter) params.set("document_type_id", typeFilter);
            if (search) params.set("search", search);
            if (dateFrom) params.set("date_from", dateFrom);
            if (dateTo) params.set("date_to", dateTo);
            if (confidenceMin) params.set("confidence_min", confidenceMin);
            if (confidenceMax) params.set("confidence_max", confidenceMax);
            window.open(`/api/v1/projects/${projectId}/documents/export?${params.toString()}`, "_blank");
          }}
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700"
          title="Export as CSV"
        >
          <FileDown className="h-4 w-4" />
          Export
        </button>
        <button
          onClick={clearFilters}
          className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-700 dark:text-surface-400 dark:hover:bg-surface-700"
          title="Clear all filters"
        >
          <RotateCcw className="h-4 w-4" />
          Clear
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : docs && docs.length > 0 ? (
        <>
          <motion.div
            variants={container}
            initial="hidden"
            animate="show"
            className="space-y-2"
          >
            {docs.map((doc) => (
              <motion.div key={doc.id} variants={cardItem}>
                <div className="flex items-center gap-2">
                  {canWrite ? (
                    <input
                      type="checkbox"
                      checked={selected.has(doc.id)}
                      onChange={() => toggle(doc.id)}
                      className="h-4 w-4 shrink-0 rounded border-surface-300 text-brand-500 focus:ring-brand-500 dark:border-surface-600"
                    />
                  ) : null}
                  <Card
                    hover
                    onClick={() => navigate(`/projects/${projectId}/documents/${doc.id}`)}
                    className="flex flex-1 items-center gap-3 px-4 py-2.5"
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
                      <FileText className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-semibold text-surface-900 dark:text-surface-100">
                          {doc.document_type_name ?? "Document"}
                        </span>
                        {getStatusBadge(doc.status)}
                      </div>
                      <p className="mt-0.5 text-xs text-surface-400">
                        {formatDate(doc.created_at)}
                        {doc.confidence_score != null
                          ? ` · Avg confidence: ${Math.round(doc.confidence_score * 100)}%`
                          : ""}
                      </p>
                    </div>
                    <div className="hidden shrink-0 text-right sm:block">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(doc.extracted_data as Record<string, unknown>)
                          .slice(0, 3)
                          .map(([key, val]) => (
                            <span
                              key={key}
                              className="rounded-lg bg-surface-100 px-2 py-0.5 text-xs text-surface-600 dark:bg-surface-700 dark:text-surface-300"
                            >
                              {Array.isArray(val)
                                ? `${val.length} items`
                                : String(val).substring(0, 20)}
                            </span>
                          ))}
                      </div>
                    </div>
                    <div className="shrink-0 text-surface-300 dark:text-surface-600">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </Card>
                </div>
              </motion.div>
            ))}
          </motion.div>

          {canWrite && selected.size > 0 ? (
            <div className="fixed bottom-8 left-1/2 z-50 max-w-[calc(100vw-2rem)] -translate-x-1/2">
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
          icon={<Inbox className="h-8 w-8" />}
          title="No documents yet"
          description="Submit documents via the API or wait for RPA bots to send them."
        />
      )}
    </div>
  );
}

import { Ban, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { useJobMutations, useProjectJobs } from "../../hooks/useExtraction";
import type { Job } from "../../types/extraction";
import { cn } from "../../lib/utils";

const STATUS_STYLES: Record<string, string> = {
  queued: "bg-surface-100 text-surface-600 dark:bg-surface-700 dark:text-surface-300",
  running: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  succeeded: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  failed: "bg-accent-100 text-accent-600 dark:bg-accent-900/30 dark:text-accent-400",
  retrying: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  cancelled: "bg-surface-100 text-surface-400 dark:bg-surface-700",
};

export function JobsPage({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, isLoading } = useProjectJobs(
    projectId,
    status ? { status } : undefined,
    3000,
  );
  const mut = useJobMutations(projectId);

  const jobs = data?.jobs ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)}
          className="rounded-xl border border-surface-300 bg-white px-3 py-2.5 text-sm dark:border-surface-600 dark:bg-surface-800">
          <option value="">All statuses</option>
          {["queued", "running", "succeeded", "failed", "retrying", "cancelled"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span className="text-xs text-surface-400">
          {data ? `${data.total} job(s)` : ""} · auto-refreshes every 3s
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-surface-400">Loading jobs…</p>
      ) : jobs.length === 0 ? (
        <Card><p className="py-8 text-center text-sm text-surface-400">No jobs yet. Upload a file or call the extract API.</p></Card>
      ) : (
        <div className="space-y-2">
          {jobs.map((job: Job) => (
            <Card key={job.id} className="px-5 py-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <button onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                      className="min-w-0 flex-1 truncate text-left font-mono text-xs text-surface-700 hover:text-brand-600 dark:text-surface-300">
                      {job.id.slice(0, 8)}… · {job.kind}
                    </button>
                    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium", STATUS_STYLES[job.status] ?? "")}>
                      {job.status}{job.attempts > 0 ? ` (try ${job.attempts})` : ""}
                    </span>
                  </div>
                  {job.error ? (
                    <p className="mt-1 truncate text-xs text-accent-500">{job.error}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                  {(job.status === "failed" || job.status === "cancelled") ? (
                    <Button variant="outline" size="sm" onClick={() => mut.retry.mutate(job.id)}>
                      <RotateCcw className="h-3.5 w-3.5" /> Retry
                    </Button>
                  ) : null}
                  {(job.status === "queued" || job.status === "running" || job.status === "retrying") ? (
                    <Button variant="ghost" size="sm" onClick={() => mut.cancel.mutate(job.id)}>
                      <Ban className="h-3.5 w-3.5" /> Cancel
                    </Button>
                  ) : null}
                </div>
              </div>
              {expanded === job.id ? (
                <pre className="mt-3 max-h-64 overflow-auto rounded-xl bg-surface-100 p-3 font-mono text-[11px] text-surface-600 dark:bg-surface-900 dark:text-surface-300">
                  {JSON.stringify({ payload: job.payload, result: job.result, usage: job.usage, error: job.error }, null, 2)}
                </pre>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

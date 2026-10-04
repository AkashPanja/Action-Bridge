import { History, Mail, Pause, Play, Plus, Trash2, FlaskConical } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { useCredentials, useProfiles, useTriggerMutations, useTriggerRuns, useTriggers } from "../../hooks/useExtraction";
import { api } from "../../lib/api";
import type { EmailTrigger, TriggerDryRun, TriggerRun } from "../../types/extraction";
import { cn, formatDate } from "../../lib/utils";

const EMPTY_FORM = {
  name: "",
  credential_id: "",
  profile_id: "",
  mode_override: "",
  folder: "INBOX",
  poll_interval_s: 300,
  sender: "",
  subject_pattern: "",
  body_pattern: "",
  must_have_attachment: true,
  allowed_types: "pdf,png,jpg,jpeg",
  max_attachment_mb: "",
  received_after: "",
  mark_read: true,
  move_to_folder: "",
  import_window: "7d",
};

const WINDOWS = [
  { id: "24h", label: "Last 24 hours" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
  { id: "unread", label: "Unread only" },
];

export function TriggersPage({ projectId }: { projectId: string }) {
  const { data: triggers, isLoading } = useTriggers(projectId);
  const { data: credentials } = useCredentials();
  const { data: profiles } = useProfiles(projectId);
  const mut = useTriggerMutations(projectId);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EmailTrigger | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [error, setError] = useState("");
  const [dryRun, setDryRun] = useState<TriggerDryRun | null>(null);
  const [dryRunning, setDryRunning] = useState<string | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);

  const mailboxes = (credentials ?? []).filter((c) => c.type === "basic" || c.type === "oauth2");

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setDryRun(null);
    setError("");
    setFormOpen(true);
  }

  function openEdit(t: EmailTrigger) {
    const cfg = t.config ?? {};
    const filters = cfg.filters ?? {};
    const after = cfg.after_action ?? {};
    setEditing(t);
    setForm({
      name: t.name,
      credential_id: t.credential_id ?? "",
      profile_id: t.profile_id ?? "",
      mode_override: t.mode_override ?? "",
      folder: cfg.folder ?? "INBOX",
      poll_interval_s: cfg.poll_interval_s ?? 300,
      sender: filters.sender ?? "",
      subject_pattern: filters.subject_pattern ?? "",
      body_pattern: filters.body_pattern ?? "",
      must_have_attachment: filters.must_have_attachment ?? true,
      allowed_types: (filters.allowed_types ?? []).join(","),
      max_attachment_mb: filters.max_attachment_mb != null ? String(filters.max_attachment_mb) : "",
      received_after: (filters.received_after ?? "").slice(0, 10),
      mark_read: after.mark_read ?? true,
      move_to_folder: after.move_to_folder ?? "",
      import_window: cfg.import_window ?? "7d",
    });
    setDryRun(null);
    setError("");
    setFormOpen(true);
  }

  const set = (k: string, v: unknown) =>
    setForm((f) => ({ ...f, [k]: v }) as typeof form);

  function buildPayload(): Record<string, unknown> {
    return {
      name: form.name.trim(),
      credential_id: form.credential_id || null,
      profile_id: form.profile_id || null,
      mode_override: form.mode_override || null,
      config: {
        folder: form.folder.trim() || "INBOX",
        poll_interval_s: Number(form.poll_interval_s) || 300,
        filters: {
          sender: form.sender.trim(),
          subject_pattern: form.subject_pattern.trim(),
          body_pattern: form.body_pattern.trim(),
          must_have_attachment: form.must_have_attachment,
          allowed_types: form.allowed_types.split(",").map((s) => s.trim()).filter(Boolean),
          ...(form.max_attachment_mb !== "" ? { max_attachment_mb: Number(form.max_attachment_mb) } : {}),
          ...(form.received_after ? { received_after: form.received_after } : {}),
        },
        after_action: {
          mark_read: form.mark_read,
          ...(form.move_to_folder.trim() ? { move_to_folder: form.move_to_folder.trim() } : {}),
        },
        import_window: form.import_window,
      },
      enabled: true,
    };
  }

  async function handleSave() {
    setError("");
    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    try {
      if (editing) await mut.update.mutateAsync({ id: editing.id, data: buildPayload() });
      else await mut.create.mutateAsync(buildPayload());
      setFormOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function handleDryRun(id: string) {
    setDryRunning(id);
    setDryRun(null);
    try {
      setDryRun(await api.triggers.dryRun(projectId, id));
    } catch (err) {
      setDryRun({ seen: 0, matched: 0, submissions_created: 0, jobs_enqueued: 0, matches: [], error: err instanceof Error ? err.message : "Failed" });
    }
    setDryRunning(null);
  }

  function stateLine(t: EmailTrigger): string {
    const s = t.state ?? {};
    if (!t.enabled) return "paused";
    if (s.alert) return "alert";
    if (s.last_run_at) return `last run ${formatDate(s.last_run_at)}`;
    return "never run";
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-surface-500">
          Watch mailboxes and turn matching emails into extraction jobs.
        </p>
        <Button size="sm" onClick={openCreate}><Plus className="h-4 w-4" /> New Trigger</Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-surface-400">Loading triggers…</p>
      ) : (triggers ?? []).length === 0 ? (
        <Card><p className="py-8 text-center text-sm text-surface-400">No email triggers yet.</p></Card>
      ) : (
        <div className="space-y-2">
          {(triggers ?? []).map((t) => (
            <Card key={t.id} className="px-5 py-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <button onClick={() => openEdit(t)} className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-surface-900 hover:text-brand-600 dark:text-surface-100">
                      <Mail className="mr-1.5 inline h-3.5 w-3.5 text-surface-400" />
                      {t.name}
                    </button>
                    <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
                      !t.enabled ? "bg-surface-100 text-surface-500 dark:bg-surface-700"
                      : t.state?.alert ? "bg-accent-100 text-accent-600 dark:bg-accent-900/30 dark:text-accent-400"
                      : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300")}>
                      {stateLine(t)}
                    </span>
                    {t.mode_override ? (
                      <span className="shrink-0 rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
                        {t.mode_override === "combined" ? "merged invoice" : "one invoice per file"}
                      </span>
                    ) : null}
                  </div>
                  {t.state?.last_error ? (
                    <p className="mt-1 truncate text-xs text-accent-500" title={t.state.last_error}>{t.state.last_error}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                  <Button variant="outline" size="sm" isLoading={dryRunning === t.id} onClick={() => handleDryRun(t.id)}>
                    <FlaskConical className="h-3.5 w-3.5" /> Dry run
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setHistoryFor(historyFor === t.id ? null : t.id)}>
                    <History className="h-3.5 w-3.5" /> History
                  </Button>
                  {t.enabled ? (
                    <Button variant="ghost" size="sm" onClick={() => mut.pause.mutate(t.id)} title="Pause">
                      <Pause className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button variant="ghost" size="sm" onClick={() => mut.resume.mutate(t.id)} title="Resume">
                      <Play className="h-4 w-4 text-emerald-500" />
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => mut.remove.mutate(t.id)} title="Delete">
                    <Trash2 className="h-4 w-4 text-accent-400" />
                  </Button>
                </div>
              </div>
              {historyFor === t.id ? <TriggerHistory projectId={projectId} triggerId={t.id} /> : null}
            </Card>
          ))}
        </div>
      )}

      {dryRun ? (
        <Card className="px-5 py-4">
          <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
            Dry run — {dryRun.matched} of {dryRun.seen} would match
          </h3>
          {dryRun.error ? (
            <p className="mt-2 text-xs text-accent-500">{dryRun.error}</p>
          ) : null}
          <div className="mt-2 max-h-56 space-y-1.5 overflow-auto">
            {dryRun.matches.map((m) => (
              <div key={m.uid} className="rounded-lg bg-surface-50 px-3 py-2 text-xs dark:bg-surface-800">
                <p className="truncate font-medium text-surface-800 dark:text-surface-200">{m.subject || "(no subject)"}</p>
                <p className="truncate text-surface-400">{m.from} · {(m.attachments ?? []).join(", ") || "no attachments"}</p>
              </div>
            ))}
            {dryRun.matches.length === 0 && !dryRun.error ? (
              <p className="text-xs text-surface-400">No matching emails found.</p>
            ) : null}
          </div>
          <div className="mt-3 flex justify-end">
            <Button variant="ghost" size="sm" onClick={() => setDryRun(null)}>Close</Button>
          </div>
        </Card>
      ) : null}

      <Dialog open={formOpen} onOpenChange={setFormOpen}
        title={editing ? `Edit Trigger — ${editing.name}` : "New Email Trigger"}
        className="sm:max-w-2xl">
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input label="Name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Vendor invoices" />
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Mailbox credential</label>
              <select value={form.credential_id} onChange={(e) => set("credential_id", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">Select mailbox…</option>
                {mailboxes.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.type})</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Extraction profile</label>
              <select value={form.profile_id} onChange={(e) => set("profile_id", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">Select profile…</option>
                <ProfilesOptions projectId={projectId} />
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Invoice mode</label>
              <select value={form.mode_override} onChange={(e) => set("mode_override", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">Follow profile</option>
                <option value="per_attachment">One invoice per PDF</option>
                <option value="combined">Merge all files into one invoice</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Input label="Folder" value={form.folder} onChange={(e) => set("folder", e.target.value)} placeholder="INBOX" />
            <Input label="Poll every (seconds)" type="number" value={String(form.poll_interval_s)} onChange={(e) => set("poll_interval_s", parseInt(e.target.value) || 300)} />
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">First import</label>
              <select value={form.import_window} onChange={(e) => set("import_window", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                {WINDOWS.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
              </select>
            </div>
          </div>
          <div className="rounded-xl bg-surface-100/70 p-4 dark:bg-surface-800/60">
            <p className="text-sm font-medium text-surface-700 dark:text-surface-300">Match rules (all must match)</p>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input label="Sender (exact, @domain, or /regex/)" value={form.sender} onChange={(e) => set("sender", e.target.value)} placeholder="invoices@vendor.com" />
              <Input label="Subject pattern (regex)" value={form.subject_pattern} onChange={(e) => set("subject_pattern", e.target.value)} placeholder="invoice" />
              <Input label="Body pattern (regex)" value={form.body_pattern} onChange={(e) => set("body_pattern", e.target.value)} placeholder="amount due" />
              <Input label="Received after (date)" type="date" value={form.received_after} onChange={(e) => set("received_after", e.target.value)} />
              <Input label="File types (comma list)" value={form.allowed_types} onChange={(e) => set("allowed_types", e.target.value)} placeholder="pdf,png,jpg" />
              <Input label="Max file MB" type="number" value={form.max_attachment_mb} onChange={(e) => set("max_attachment_mb", e.target.value)} placeholder="25" />
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-surface-700 dark:text-surface-300">
              <input type="checkbox" checked={form.must_have_attachment} onChange={(e) => set("must_have_attachment", e.target.checked)}
                className="rounded border-surface-300 text-brand-600 focus:ring-brand-500" />
              Only emails with attachments
            </label>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="flex items-end gap-2 pb-3 text-sm text-surface-700 dark:text-surface-300">
              <input type="checkbox" checked={form.mark_read} onChange={(e) => set("mark_read", e.target.checked)}
                className="rounded border-surface-300 text-brand-600 focus:ring-brand-500" />
              Mark as read after processing
            </label>
            <Input label="Move to folder (optional)" value={form.move_to_folder} onChange={(e) => set("move_to_folder", e.target.value)} placeholder="Processed" />
          </div>
          {error ? (
            <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSave}>Save Trigger</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

function ProfilesOptions({ projectId }: { projectId: string }) {
  const { data } = useProfiles(projectId);
  return (
    <>
      {(data ?? []).map((p: { id: string; name: string }) => (
        <option key={p.id} value={p.id}>{p.name}</option>
      ))}
    </>
  );
}

function TriggerHistory({ projectId, triggerId }: { projectId: string; triggerId: string }) {
  const { data } = useTriggerRuns(projectId, triggerId);
  const runs = (data ?? []) as TriggerRun[];
  if (runs.length === 0) {
    return <p className="mt-3 text-xs text-surface-400">No runs yet.</p>;
  }
  return (
    <div className="mt-3 space-y-1.5">
      {runs.slice(0, 10).map((r) => (
        <div key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded-lg bg-surface-50 px-3 py-2 text-xs dark:bg-surface-800">
          <span className="text-surface-500">{r.started_at ? formatDate(r.started_at) : "—"}</span>
          {r.dry_run ? <span className="rounded-full bg-surface-200 px-2 py-0.5 text-[10px] dark:bg-surface-700">dry run</span> : null}
          <span className="text-surface-600 dark:text-surface-300">seen {r.seen} · matched {r.matched} · submissions {r.submissions_created} · jobs {r.jobs_enqueued}</span>
          {r.error ? <span className="truncate text-accent-500" title={r.error}>{r.error}</span> : null}
        </div>
      ))}
    </div>
  );
}

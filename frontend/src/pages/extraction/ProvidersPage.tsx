import { FlaskConical, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { useCredentialMutations, useCredentials } from "../../hooks/useExtraction";
import { useProviderMutations, useProviders } from "../../hooks/useExtraction";
import { api } from "../../lib/api";
import type { Provider, ProviderTestResult } from "../../types/extraction";
import { cn } from "../../lib/utils";

const EMPTY = {
  name: "", kind: "openai_compatible", base_url: "http://localhost:11434/v1",
  credential_id: "", model: "actionbridge-qwen25-3b", vision: false,
  json_schema: false, json_object: true, max_concurrency: 1,
  timeout_s: 120, is_local: true, context_window: 8192, enabled: true,
};

export function ProvidersPage() {
  const { data: providers, isLoading } = useProviders();
  const { data: credentials } = useCredentials();
  const mut = useProviderMutations();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Provider | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({ ...EMPTY });
  const [error, setError] = useState("");
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ProviderTestResult>>({});

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY });
    setError("");
    setFormOpen(true);
  }

  function openEdit(p: Provider) {
    setEditing(p);
    setForm({ ...EMPTY, ...p, credential_id: p.credential_id ?? "" });
    setError("");
    setFormOpen(true);
  }

  async function handleSave() {
    setError("");
    const payload: Record<string, unknown> = { ...form };
    if (!payload.credential_id) delete payload.credential_id;
    if (!payload.context_window) delete payload.context_window;
    try {
      if (editing) await mut.update.mutateAsync({ id: editing.id, data: payload });
      else await mut.create.mutateAsync(payload);
      setFormOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function handleTest(p: Provider) {
    setTesting(p.id);
    try {
      const res = await api.providers.test(p.id);
      setResults((r) => ({ ...r, [p.id]: res }));
    } catch (err) {
      setResults((r) => ({
        ...r, [p.id]: { ok: false, detail: err instanceof Error ? err.message : "Failed", latency_ms: 0 },
      }));
    }
    setTesting(null);
  }

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-surface-500">
          Local Ollama is pre-seeded. Add cloud models alongside it; profiles choose the order to try.
        </p>
        <Button size="sm" onClick={openCreate}><Plus className="h-4 w-4" /> Add Provider</Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-surface-400">Loading providers…</p>
      ) : (providers ?? []).length === 0 ? (
        <Card><p className="py-8 text-center text-sm text-surface-400">No providers yet.</p></Card>
      ) : (
        <div className="space-y-2">
          {(providers ?? []).map((p) => {
            const res = results[p.id];
            return (
              <Card key={p.id} className="px-5 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <div className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                      p.is_local
                        ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400"
                        : "bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-400",
                    )}>
                      <span className="text-xs font-bold">{p.is_local ? "LO" : "CL"}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <button onClick={() => openEdit(p)} className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-surface-900 hover:text-brand-600 dark:text-surface-100">
                          {p.name}
                        </button>
                        {p.is_local ? (
                          <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">local</span>
                        ) : (
                          <span className="shrink-0 rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-900/30 dark:text-sky-300">cloud</span>
                        )}
                        {!p.enabled ? (
                          <span className="shrink-0 rounded-full bg-surface-100 px-2 py-0.5 text-[10px] font-medium text-surface-500">disabled</span>
                        ) : null}
                      </div>
                      <p className="mt-0.5 truncate font-mono text-xs text-surface-400">
                        {p.model} · {p.kind} · conc {p.max_concurrency}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                    <Button variant="outline" size="sm" isLoading={testing === p.id} onClick={() => handleTest(p)}>
                      <FlaskConical className="h-3.5 w-3.5" /> Test
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => mut.remove.mutate(p.id)} title="Delete">
                      <Trash2 className="h-4 w-4 text-accent-400" />
                    </Button>
                  </div>
                </div>
                {res ? (
                  <p className={cn(
                    "mt-3 rounded-xl px-4 py-2 text-xs",
                    res.ok
                      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300"
                      : "bg-accent-50 text-accent-600 dark:bg-accent-900/20 dark:text-accent-400",
                  )}>
                    {res.ok
                      ? `OK in ${res.latency_ms} ms · mode ${res.json_mode} · JSON ${res.json_ok ? "valid" : "check prompts"}`
                      : `Failed: ${res.detail}`}
                  </p>
                ) : null}
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen} title={editing ? "Edit Provider" : "Add Provider"} className="max-w-xl">
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input label="Name" value={String(form.name ?? "")} onChange={(e) => set("name", e.target.value)} placeholder="Local Ollama" />
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Kind</label>
              <select value={String(form.kind ?? "openai_compatible")} onChange={(e) => set("kind", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="openai_compatible">OpenAI-compatible</option>
                <option value="anthropic">Anthropic (Claude)</option>
              </select>
            </div>
          </div>
          <Input label="Base URL" value={String(form.base_url ?? "")} onChange={(e) => set("base_url", e.target.value)} placeholder="http://localhost:11434/v1" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input label="Model" value={String(form.model ?? "")} onChange={(e) => set("model", e.target.value)} placeholder="actionbridge-qwen25-3b" />
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Credential (API key)</label>
              <select value={String(form.credential_id ?? "")} onChange={(e) => set("credential_id", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">None (e.g. local Ollama)</option>
                {(credentials ?? []).filter((c) => c.type === "api_key").map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.hint})</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Input label="Concurrency" type="number" value={String(form.max_concurrency ?? 1)} onChange={(e) => set("max_concurrency", parseInt(e.target.value) || 1)} />
            <Input label="Timeout (s)" type="number" value={String(form.timeout_s ?? 120)} onChange={(e) => set("timeout_s", parseFloat(e.target.value) || 120)} />
            <Input label="Context window" type="number" value={String(form.context_window ?? "")} onChange={(e) => set("context_window", parseInt(e.target.value) || "")} placeholder="8192" />
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            {([["vision", "Vision"], ["json_schema", "JSON schema mode"], ["json_object", "JSON object mode"], ["is_local", "Runs on this machine"], ["enabled", "Enabled"]] as const).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-surface-700 dark:text-surface-300">
                <input type="checkbox" checked={Boolean(form[k])} onChange={(e) => set(k, e.target.checked)}
                  className="rounded border-surface-300 text-brand-600 focus:ring-brand-500" />
                {label}
              </label>
            ))}
          </div>
          {error ? (
            <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} isLoading={mut.create.isPending || mut.update.isPending}>Save Provider</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

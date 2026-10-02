import { FlaskConical, KeyRound, ListPlus, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { OllamaModelsPanel } from "../../components/extraction/OllamaModelsPanel";
import { useCredentialMutations, useCredentials } from "../../hooks/useExtraction";
import { useProviderMutations, useProviderPresets, useProviders } from "../../hooks/useExtraction";
import { api } from "../../lib/api";
import type { Provider, ProviderPreset } from "../../types/extraction";
import { cn } from "../../lib/utils";

const EMPTY = {
  name: "", kind: "openai_compatible", base_url: "http://localhost:11434/v1",
  credential_id: "", model: "actionbridge-qwen25-3b", vision: false,
  json_schema: false, json_object: true, max_concurrency: 1,
  timeout_s: 120, is_local: true, context_window: 8192, enabled: true,
};

function presetInitials(name: string) {
  return name.split(/[\s(]+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}

export function ProvidersPage() {
  const { data: providers, isLoading } = useProviders();
  const { data: presets } = useProviderPresets();
  const { data: credentials } = useCredentials();
  const mut = useProviderMutations();
  const credMut = useCredentialMutations();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Provider | null>(null);
  const [activePreset, setActivePreset] = useState<ProviderPreset | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({ ...EMPTY });
  const [extraHeadersText, setExtraHeadersText] = useState("{}");
  const [newKey, setNewKey] = useState("");
  const [modelOptions, setModelOptions] = useState<string[] | null>(null);
  const [modelMsg, setModelMsg] = useState("");
  const [fetchingModels, setFetchingModels] = useState(false);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; detail: string; latency_ms: number }>>({});

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  function openOllamaModel(model: string, baseUrl: string) {
    const local = /^(https?:\/\/)?(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i.test(baseUrl.trim());
    setEditing(null);
    setActivePreset(null);
    setForm({
      ...EMPTY,
      name: `Ollama ${model}`,
      kind: "openai_compatible",
      base_url: `${baseUrl.trim().replace(/\/+$/, "")}/v1`,
      model,
      json_object: true,
      json_schema: false,
      is_local: local,
      max_concurrency: 1,
    });
    setExtraHeadersText("{}");
    setNewKey("");
    setModelOptions(null);
    setModelMsg("");
    setError("");
    setFormOpen(true);
  }

  function openCreate() {
    setEditing(null);
    setActivePreset(null);
    setForm({ ...EMPTY });
    setExtraHeadersText("{}");
    setNewKey("");
    setModelOptions(null);
    setModelMsg("");
    setError("");
    setFormOpen(true);
  }

  function openQuickAdd(preset: ProviderPreset) {
    setEditing(null);
    setActivePreset(preset);
    setForm({
      ...EMPTY,
      name: preset.name,
      kind: preset.kind,
      base_url: preset.base_url,
      model: preset.default_model,
      vision: preset.vision,
      json_schema: preset.json_schema,
      json_object: preset.json_object,
      is_local: preset.is_local,
      context_window: preset.context_window ?? "",
      max_concurrency: preset.is_local ? 1 : 4,
    });
    setExtraHeadersText(JSON.stringify(preset.extra_headers ?? {}, null, 2));
    setNewKey("");
    setModelOptions(null);
    setModelMsg("");
    setError("");
    setFormOpen(true);
  }

  function openEdit(p: Provider) {    setEditing(p);
    setActivePreset(null);
    setForm({ ...EMPTY, ...p, credential_id: p.credential_id ?? "" });
    setExtraHeadersText(JSON.stringify(p.extra_headers ?? {}, null, 2));
    setNewKey("");
    setModelOptions(null);
    setModelMsg("");
    setError("");
    setFormOpen(true);
  }

  function parseHeaders(): Record<string, string> {
    const text = extraHeadersText.trim() || "{}";
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Extra headers must be a JSON object");
    }
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v !== "string") throw new Error(`Header "${k}" must be a string`);
    }
    return parsed as Record<string, string>;
  }

  async function handleSave() {
    setError("");
    let headers: Record<string, string>;
    try {
      headers = parseHeaders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bad headers JSON");
      return;
    }
    const payload: Record<string, unknown> = { ...form, extra_headers: headers };
    if (!payload.credential_id || payload.credential_id === "__new__") delete payload.credential_id;
    if (!payload.context_window) delete payload.context_window;
    try {
      if (editing) {
        await mut.update.mutateAsync({ id: editing.id, data: payload });
      } else {
        let credentialId = typeof form.credential_id === "string" ? form.credential_id : "";
        if (form.credential_id === "__new__") {
          if (!newKey.trim()) {
            setError("Paste the new API key");
            return;
          }
          const created = await credMut.create.mutateAsync({
            name: `${String(form.name || "provider").trim()} key`,
            type: "api_key",
            payload: { api_key: newKey.trim() },
          });
          credentialId = created.id;
        }
        if (credentialId) payload.credential_id = credentialId;
        const created = await mut.create.mutateAsync(payload);
        // Immediate proof it works.
        setFormOpen(false);
        await handleTest({ ...created, credential_id: created.credential_id ?? null } as Provider);
        return;
      }
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

  async function handleFetchModels() {
    if (!editing) return;
    setFetchingModels(true);
    setModelMsg("");
    try {
      const res = await api.providers.models(editing.id);
      if (res.supported && res.models.length > 0) {
        setModelOptions(res.models.slice(0, 200));
        if (!res.models.includes(String(form.model ?? ""))) {
          set("model", res.models[0]);
        }
        setModelMsg(res.detail);
      } else {
        setModelOptions(null);
        setModelMsg(res.detail || "This endpoint does not list models — type the model id.");
      }
    } catch (err) {
      setModelMsg(err instanceof Error ? err.message : "Fetch failed");
    }
    setFetchingModels(false);
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Local Ollama models</h3>
        <p className="mt-0.5 text-xs text-surface-400">
          Anything installed (or pulled) in Ollama can back a provider — no fixed model list.
        </p>
        <div className="mt-3">
          <OllamaModelsPanel onUseModel={openOllamaModel} />
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">Cloud runners — quick add</h3>
        <p className="mt-0.5 text-xs text-surface-400">
          Pick a runner, paste a key, done. Local Ollama stays pre-seeded below.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {(presets ?? []).filter((p) => !p.is_local).map((p) => (
            <button key={p.id} type="button" onClick={() => openQuickAdd(p)}
              className="group rounded-2xl border border-surface-200 bg-white p-4 text-left transition-all hover:border-brand-400 hover:shadow-lg dark:border-surface-700 dark:bg-surface-800">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#1b2cc7] to-[#2f7de9] text-xs font-bold text-white">
                {presetInitials(p.name)}
              </div>
              <p className="mt-2 truncate text-sm font-semibold text-surface-900 group-hover:text-brand-600 dark:text-surface-100">
                {p.name}
              </p>
              <p className="truncate font-mono text-[10px] text-surface-400">
                {p.base_url.replace(/^https?:\/\//, "")}
              </p>
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">All providers</h3>
          <Button size="sm" onClick={openCreate}><Plus className="h-4 w-4" /> Add Manually</Button>
        </div>

        {isLoading ? (
          <p className="mt-3 text-sm text-surface-400">Loading providers…</p>
        ) : (providers ?? []).length === 0 ? (
          <Card><p className="py-8 text-center text-sm text-surface-400">No providers yet.</p></Card>
        ) : (
          <div className="mt-3 space-y-2">
            {(providers ?? []).map((p) => {
              const res = results[p.id];
              return (
                <Card key={p.id} className="px-5 py-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <div className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-bold",
                        p.is_local
                          ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400"
                          : "bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-400",
                      )}>
                        {p.is_local ? "LO" : "CL"}
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
                        ? `OK — test passed${"latency_ms" in res ? ` in ${res.latency_ms} ms` : ""}`
                        : `Failed: ${res.detail}`}
                    </p>
                  ) : null}
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <Dialog open={formOpen} onOpenChange={setFormOpen}
        title={editing ? "Edit Provider" : activePreset ? `Add ${activePreset.name}` : "Add Provider"}
        description={activePreset ? activePreset.notes : undefined}
        className="max-w-xl">
        <div className="space-y-4">
          {activePreset?.key_url ? (
            <p className="rounded-xl bg-surface-100 px-4 py-2 text-xs text-surface-500 dark:bg-surface-800">
              Get a key: <a href={activePreset.key_url} target="_blank" rel="noreferrer" className="font-medium text-brand-600 hover:underline">{activePreset.key_url.replace(/^https?:\/\//, "")}</a>
            </p>
          ) : null}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input label="Name" value={String(form.name ?? "")} onChange={(e) => set("name", e.target.value)} placeholder="My OpenAI" />
            {!editing ? (
              <div>
                <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Kind</label>
                <select value={String(form.kind ?? "openai_compatible")} onChange={(e) => set("kind", e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                  <option value="openai_compatible">OpenAI-compatible</option>
                  <option value="anthropic">Anthropic (Claude)</option>
                </select>
              </div>
            ) : null}
          </div>
          <Input label="Base URL" value={String(form.base_url ?? "")} onChange={(e) => set("base_url", e.target.value)} />
          <div>
            <div className="flex items-end justify-between gap-2">
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Model</label>
              {editing ? (
                <button type="button" onClick={handleFetchModels} disabled={fetchingModels}
                  className="flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50">
                  <ListPlus className="h-3.5 w-3.5" /> {fetchingModels ? "Fetching…" : "Fetch models"}
                </button>
              ) : null}
            </div>
            {modelOptions ? (
              <select value={String(form.model ?? "")} onChange={(e) => set("model", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <Input label="" value={String(form.model ?? "")} onChange={(e) => set("model", e.target.value)} placeholder="gpt-4o-mini" />
            )}
            {modelMsg ? <p className="mt-1 text-xs text-surface-400">{modelMsg}</p> : null}
          </div>
          <div>
            <label className="text-sm font-medium text-surface-700 dark:text-surface-300">API key</label>
            <select value={String(form.credential_id ?? "")} onChange={(e) => set("credential_id", e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
              <option value="">None (e.g. local Ollama)</option>
              {(credentials ?? []).filter((c) => c.type === "api_key").map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.hint})</option>
              ))}
              <option value="__new__">+ Paste a new key…</option>
            </select>
            {form.credential_id === "__new__" ? (
              <div className="mt-2 flex items-center gap-2 rounded-xl border border-transparent bg-surface-100 px-4 py-1 dark:bg-surface-800">
                <KeyRound className="h-4 w-4 shrink-0 text-surface-400" />
                <input type="password" value={newKey} onChange={(e) => setNewKey(e.target.value)}
                  placeholder="Paste API key — stored encrypted"
                  className="w-full bg-transparent py-2.5 text-sm focus:outline-none" />
              </div>
            ) : null}
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Input label="Concurrency" type="number" value={String(form.max_concurrency ?? 1)} onChange={(e) => set("max_concurrency", parseInt(e.target.value) || 1)} />
            <Input label="Timeout (s)" type="number" value={String(form.timeout_s ?? 120)} onChange={(e) => set("timeout_s", parseFloat(e.target.value) || 120)} />
            <Input label="Context window" type="number" value={String(form.context_window ?? "")} onChange={(e) => set("context_window", parseInt(e.target.value) || "")} placeholder="8192" />
          </div>
          <div>
            <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
              Extra headers <span className="font-normal text-surface-400">(JSON — e.g. OpenRouter referrer)</span>
            </label>
            <textarea value={extraHeadersText} onChange={(e) => setExtraHeadersText(e.target.value)} rows={2}
              placeholder='{}'
              className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 font-mono text-xs dark:bg-surface-800" />
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
            <Button onClick={handleSave} isLoading={mut.create.isPending || mut.update.isPending || credMut.create.isPending}>
              Save Provider
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

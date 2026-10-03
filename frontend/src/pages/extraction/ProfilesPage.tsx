import { FlaskConical, Pencil, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { useDocumentTypes } from "../../hooks/useDocumentTypes";
import {
  useBuiltinPromptTemplates,
  useProfileMutations,
  useProfiles,
  usePromptTemplateMutations,
  usePromptTemplates,
  useProviders,
} from "../../hooks/useExtraction";
import { api } from "../../lib/api";
import type { ExtractionProfile, PlaygroundResult, PromptTemplate } from "../../types/extraction";
import { cn } from "../../lib/utils";

interface Candidate {
  document_type_id: string;
  name?: string;
  ignore?: boolean;
}

const EMPTY_FORM = {
  name: "",
  mode: "per_attachment",
  candidates: [] as Candidate[],
  target_document_type_id: "",
  system: "",
  extraction: "",
  classification: "",
  chain: [] as string[],
  ocr_provider_id: "",
  allow_cloud: false,
};

export function ProfilesPage({ projectId }: { projectId: string }) {
  const { data: profiles, isLoading } = useProfiles(projectId);
  const { data: docTypes } = useDocumentTypes(projectId);
  const { data: providers } = useProviders();
  const mut = useProfileMutations(projectId);
  const { data: builtinTemplates } = useBuiltinPromptTemplates();
  const { data: savedTemplates } = usePromptTemplates(projectId);
  const templateMut = usePromptTemplateMutations(projectId);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ExtractionProfile | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [error, setError] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templateShared, setTemplateShared] = useState(false);
  const [templateSaved, setTemplateSaved] = useState(false);

  const [pgText, setPgText] = useState("");
  const [pgFile, setPgFile] = useState<File | null>(null);
  const [pgRunning, setPgRunning] = useState(false);
  const [pgResult, setPgResult] = useState<PlaygroundResult | null>(null);

  const typeName = (id: string) =>
    (docTypes ?? []).find((t) => t.id === id)?.name ?? id.slice(0, 8);
  const providerName = (id: string) =>
    (providers ?? []).find((p) => p.id === id)?.name ?? id.slice(0, 8);

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setTemplateName("");
    setTemplateShared(false);
    setTemplateSaved(false);
    setPgText("");
    setPgFile(null);
    setPgResult(null);
    setError("");
    setFormOpen(true);
  }

  function openEdit(p: ExtractionProfile) {
    setEditing(p);
    setTemplateName("");
    setTemplateShared(false);
    setTemplateSaved(false);
    setForm({
      name: p.name,
      mode: p.mode,
      candidates: (p.candidate_types ?? []).map((c) => ({ ...c })),
      target_document_type_id: p.target_document_type_id ?? "",
      system: p.prompts?.system ?? "",
      extraction: p.prompts?.extraction ?? "",
      classification: p.prompts?.classification ?? "",
      chain: [...(p.provider_chain ?? [])],
      ocr_provider_id: p.ocr_provider_id ?? "",
      allow_cloud: p.allow_cloud,
    });
    setPgText("");
    setPgFile(null);
    setPgResult(null);
    setError("");
    setFormOpen(true);
  }

  const set = (k: string, v: unknown) =>
    setForm((f) => ({ ...f, [k]: v }) as typeof form);

  function toggleCandidate(typeId: string, typeName_: string) {
    setForm((f) => {
      const has = f.candidates.some((c) => c.document_type_id === typeId);
      return {
        ...f,
        candidates: has
          ? f.candidates.filter((c) => c.document_type_id !== typeId)
          : [...f.candidates, { document_type_id: typeId, name: typeName_ }],
      };
    });
  }

  function toggleIgnore(typeId: string) {
    setForm((f) => ({
      ...f,
      candidates: f.candidates.map((c) =>
        c.document_type_id === typeId ? { ...c, ignore: !c.ignore } : c,
      ),
    }));
  }

  function toggleChain(id: string) {
    setForm((f) => ({
      ...f,
      chain: f.chain.includes(id) ? f.chain.filter((x) => x !== id) : [...f.chain, id],
    }));
  }

  function applyTemplate(template: PromptTemplate) {
    const prompts = template.prompts ?? {};
    setForm((f) => ({
      ...f,
      system: typeof prompts.system === "string" ? prompts.system : f.system,
      extraction: typeof prompts.extraction === "string" ? prompts.extraction : f.extraction,
      classification: typeof prompts.classification === "string" ? prompts.classification : f.classification,
    }));
    setTemplateSaved(false);
    setError("");
  }

  async function handleSaveTemplate() {
    setError("");
    if (!templateName.trim()) {
      setError("Give the template a name first");
      return;
    }
    try {
      await templateMut.create.mutateAsync({
        name: templateName.trim(),
        prompts: {
          ...(form.system ? { system: form.system } : {}),
          ...(form.extraction ? { extraction: form.extraction } : {}),
          ...(form.classification ? { classification: form.classification } : {}),
        },
        is_shared: templateShared,
      });
      setTemplateName("");
      setTemplateShared(false);
      setTemplateSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function handleSave() {
    setError("");
    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      mode: form.mode,
      candidate_types: form.candidates,
      target_document_type_id: form.target_document_type_id || null,
      prompts: {
        ...(form.system ? { system: form.system } : {}),
        ...(form.extraction ? { extraction: form.extraction } : {}),
        ...(form.classification ? { classification: form.classification } : {}),
      },
      provider_chain: form.chain,
      ocr_provider_id: form.ocr_provider_id || null,
      allow_cloud: form.allow_cloud,
    };
    try {
      if (editing) await mut.update.mutateAsync({ id: editing.id, data: payload });
      else await mut.create.mutateAsync(payload);
      setFormOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function handlePlayground() {
    if (!editing) return;
    setPgRunning(true);
    setPgResult(null);
    try {
      const fd = new FormData();
      if (pgText.trim()) fd.append("text", pgText.trim());
      if (pgFile) fd.append("file", pgFile);
      const res = await api.profiles.playground(projectId, editing.id, fd);
      setPgResult(res);
    } catch (err) {
      setPgResult({ data: null, errors: [err instanceof Error ? err.message : "Failed"], latency_ms: 0 });
    }
    setPgRunning(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-surface-500">
          Profiles decide how uploads and triggers are read: mode, prompts, and provider order.
        </p>
        <Button size="sm" onClick={openCreate}><Plus className="h-4 w-4" /> New Profile</Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-surface-400">Loading profiles…</p>
      ) : (profiles ?? []).length === 0 ? (
        <Card><p className="py-8 text-center text-sm text-surface-400">No extraction profiles yet.</p></Card>
      ) : (
        <div className="space-y-2">
          {(profiles ?? []).map((p) => (
            <Card key={p.id} className="px-5 py-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <button onClick={() => openEdit(p)} className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-surface-900 hover:text-brand-600 dark:text-surface-100">
                      {p.name}
                    </button>
                    <span className="shrink-0 rounded-full bg-surface-100 px-2 py-0.5 text-[10px] font-medium text-surface-600 dark:bg-surface-700 dark:text-surface-300">
                      {p.mode === "combined" ? "combined" : "per file"} · v{p.version}
                    </span>
                    {!p.allow_cloud ? (
                      <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">local only</span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-surface-400">
                    {(p.provider_chain ?? []).map(providerName).join(" → ") || "no providers"}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                  <Button variant="outline" size="sm" onClick={() => openEdit(p)}>
                    <Pencil className="h-3.5 w-3.5" /> Edit + Playground
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => mut.remove.mutate(p.id)} title="Delete">
                    <Trash2 className="h-4 w-4 text-accent-400" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}
        title={editing ? `Edit Profile — ${editing.name}` : "New Extraction Profile"}
        className="sm:max-w-2xl">
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input label="Name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Invoices" />
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Mode</label>
              <select value={form.mode} onChange={(e) => set("mode", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="per_attachment">Per file (classify → extract)</option>
                <option value="combined">Combined (all files → one JSON)</option>
              </select>
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-surface-700 dark:text-surface-300">Candidate document types</p>
            <p className="text-xs text-surface-400">Checked types are classified; “ignore” skips the file but lists it.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(docTypes ?? []).map((t) => {
                const sel = form.candidates.find((c) => c.document_type_id === t.id);
                return (
                  <span key={t.id} className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium",
                    sel ? "bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                      : "bg-surface-100 text-surface-500 dark:bg-surface-700 dark:text-surface-400",
                  )}>
                    <button type="button" onClick={() => toggleCandidate(t.id, t.name)}>{t.name}</button>
                    {sel ? (
                      <button type="button" onClick={() => toggleIgnore(t.id)}
                        title="Toggle ignore"
                        className={cn("rounded px-1 text-[10px]", sel.ignore ? "bg-amber-200 text-amber-800" : "bg-white/60 text-surface-400")}>
                        {sel.ignore ? "ignored" : "ignore?"}
                      </button>
                    ) : null}
                  </span>
                );
              })}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
              Target type {form.mode === "combined" ? "(required)" : "(for manual-entry fallback)"}
            </label>
            <select value={form.target_document_type_id} onChange={(e) => set("target_document_type_id", e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
              <option value="">None</option>
              {(docTypes ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>

          <div>
            <p className="text-sm font-medium text-surface-700 dark:text-surface-300">Provider chain (tried in order)</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(providers ?? []).filter((p) => p.enabled).map((p) => {
                const idx = form.chain.indexOf(p.id);
                return (
                  <button key={p.id} type="button" onClick={() => toggleChain(p.id)}
                    className={cn(
                      "rounded-lg px-3 py-1.5 text-xs font-medium",
                      idx >= 0 ? "bg-brand-600 text-white" : "bg-surface-100 text-surface-500 dark:bg-surface-700 dark:text-surface-400",
                    )}>
                    {idx >= 0 ? `${idx + 1}. ` : ""}{p.name}{p.is_local ? " (local)" : ""}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">OCR provider (scans)</label>
              <select value={form.ocr_provider_id} onChange={(e) => set("ocr_provider_id", e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">None (manual entry)</option>
                {(providers ?? []).filter((p) => p.vision).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <label className="flex items-end gap-2 pb-3 text-sm text-surface-700 dark:text-surface-300">
              <input type="checkbox" checked={form.allow_cloud} onChange={(e) => set("allow_cloud", e.target.checked)}
                className="rounded border-surface-300 text-brand-600 focus:ring-brand-500" />
              Allow cloud providers
            </label>
          </div>

          <div className="space-y-3">
            <p className="text-sm font-medium text-surface-700 dark:text-surface-300">Prompts (blank = built-in defaults)</p>
            <div>
              <p className="mb-2 text-xs text-surface-400">Start from a template — click to fill the boxes below, then modify freely. Your edits never change the template.</p>
              <div className="flex flex-wrap gap-2">
                {(builtinTemplates ?? []).map((t) => (
                  <button key={t.id} type="button" onClick={() => applyTemplate(t)} title={t.description ?? t.name}
                    className="rounded-lg bg-brand-100 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-200 dark:bg-brand-900/30 dark:text-brand-300">
                    {t.name}
                  </button>
                ))}
                {(savedTemplates ?? []).map((t) => (
                  <span key={t.id} className="flex items-center gap-1 rounded-lg bg-surface-100 px-2 py-1 text-xs dark:bg-surface-700">
                    <button type="button" onClick={() => applyTemplate(t)} title={t.description ?? t.name}
                      className="font-medium text-surface-600 hover:text-brand-600 dark:text-surface-300">
                      {t.name}{t.is_shared ? " (shared)" : ""}
                    </button>
                    {!t.builtin && (t.project_id === projectId) ? (
                      <button type="button" title="Delete template"
                        onClick={() => templateMut.remove.mutate(t.id)}
                        className="rounded p-0.5 text-surface-400 hover:text-accent-500">
                        <Trash2 className="h-3 w-3" />
                      </button>
                    ) : null}
                  </span>
                ))}
              </div>
            </div>
            {(["system", "extraction", "classification"] as const).map((k) => (
              <div key={k}>
                <label className="text-xs font-medium capitalize text-surface-500">{k}</label>
                <textarea value={form[k]} onChange={(e) => set(k, e.target.value)} rows={k === "system" ? 3 : 4}
                  placeholder="Leave blank for the built-in default"
                  className="mt-1 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 font-mono text-xs dark:bg-surface-800" />
              </div>
            ))}
            <div className="rounded-xl bg-surface-100/70 p-3 dark:bg-surface-800/60">
              <div className="flex flex-wrap items-center gap-2">
                <Input label="" value={templateName} onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="Save current prompts as template…" />
                <label className="flex items-center gap-1.5 text-xs text-surface-500">
                  <input type="checkbox" checked={templateShared} onChange={(e) => setTemplateShared(e.target.checked)}
                    className="rounded border-surface-300 text-brand-600 focus:ring-brand-500" />
                  Share with all projects
                </label>
                <Button size="sm" variant="outline" onClick={handleSaveTemplate}
                  isLoading={templateMut.create.isPending}>
                  <Save className="h-3.5 w-3.5" /> Save template
                </Button>
              </div>
              {templateSaved ? (
                <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">Template saved — find it above next time.</p>
              ) : null}
            </div>
          </div>

          {editing ? (
            <div className="rounded-xl border border-surface-200 p-4 dark:border-surface-700">
              <p className="flex items-center gap-1.5 text-sm font-medium text-surface-700 dark:text-surface-300">
                <FlaskConical className="h-4 w-4" /> Playground — runs prompts, creates nothing
              </p>
              <textarea value={pgText} onChange={(e) => setPgText(e.target.value)} rows={3}
                placeholder="Paste document text here…"
                className="mt-2 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 font-mono text-xs dark:bg-surface-800" />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <label className="cursor-pointer rounded-lg border border-surface-300 px-3 py-1.5 text-xs dark:border-surface-600">
                  {pgFile ? pgFile.name : "Or choose a file"}
                  <input type="file" className="hidden" onChange={(e) => setPgFile(e.target.files?.[0] ?? null)} />
                </label>
                <Button size="sm" onClick={handlePlayground} isLoading={pgRunning}>Run</Button>
              </div>
              {pgResult ? (
                <div className="mt-3">
                  {pgResult.errors.length > 0 ? (
                    <p className="rounded-xl bg-accent-50 px-4 py-2 text-xs text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">
                      {pgResult.errors.join("; ")}
                    </p>
                  ) : null}
                  {pgResult.data ? (
                    <pre className="mt-2 max-h-56 overflow-auto rounded-xl bg-surface-100 p-3 font-mono text-[11px] dark:bg-surface-900">
                      {JSON.stringify(pgResult.data, null, 2)}
                    </pre>
                  ) : null}
                  <p className="mt-1 text-[11px] text-surface-400">
                    {pgResult.provider} · {pgResult.model} · {pgResult.latency_ms} ms
                    {pgResult.classification ? ` · classified: ${pgResult.classification}` : ""}
                  </p>
                </div>
              ) : null}
            </div>
          ) : null}

          {error ? (
            <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} isLoading={mut.create.isPending || mut.update.isPending}>Save Profile</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

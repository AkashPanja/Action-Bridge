import { FlaskConical, KeyRound, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { useCredentialMutations, useCredentials } from "../../hooks/useExtraction";
import { api } from "../../lib/api";
import type { Credential } from "../../types/extraction";
import { cn } from "../../lib/utils";

const SECRET_FIELDS: Record<string, { key: string; label: string }[]> = {
  api_key: [{ key: "api_key", label: "API Key" }],
  basic: [{ key: "password", label: "Password" }],
  oauth2: [
    { key: "client_secret", label: "Client Secret" },
    { key: "refresh_token", label: "Refresh Token" },
  ],
};

export function CredentialsPage() {
  const { data: credentials, isLoading } = useCredentials();
  const mut = useCredentialMutations();
  const [formOpen, setFormOpen] = useState(false);
  const [replacing, setReplacing] = useState<Credential | null>(null);
  const [ctype, setCtype] = useState("api_key");
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; detail: string }>>({});

  function openCreate() {
    setReplacing(null);
    setCtype("api_key");
    setName("");
    setHost("");
    setUsername("");
    setSecrets({});
    setNotes("");
    setError("");
    setFormOpen(true);
  }

  function openReplace(c: Credential) {
    setReplacing(c);
    setCtype(c.type);
    setName(c.name);
    const meta = (c.meta ?? {}) as Record<string, string>;
    setHost(meta.host ?? "");
    setUsername(meta.username ?? "");
    setSecrets({});
    setNotes("");
    setError("");
    setFormOpen(true);
  }

  function buildPayload(): Record<string, unknown> {
    const payload: Record<string, unknown> = { notes };
    if (host) payload.host = host;
    if (username) payload.username = username;
    for (const { key } of SECRET_FIELDS[ctype] ?? []) {
      if (secrets[key]) payload[key] = secrets[key];
    }
    return payload;
  }

  async function handleSave() {
    setError("");
    if (!replacing && !name.trim()) {
      setError("Name is required");
      return;
    }
    try {
      if (replacing) {
        await mut.replaceSecret.mutateAsync({ id: replacing.id, payload: buildPayload() });
      } else {
        await mut.create.mutateAsync({ name: name.trim(), type: ctype, payload: buildPayload() });
      }
      setFormOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function handleTest(c: Credential) {
    setTesting(c.id);
    try {
      const res = await api.credentials.test(c.id);
      setResults((r) => ({ ...r, [c.id]: res }));
    } catch (err) {
      setResults((r) => ({ ...r, [c.id]: { ok: false, detail: err instanceof Error ? err.message : "Failed" } }));
    }
    setTesting(null);
  }

  async function handleDelete(c: Credential) {
    if (!confirm(`Delete credential "${c.name}"?`)) return;
    setError("");
    try {
      await mut.remove.mutateAsync(c.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-surface-500">
          Secrets are encrypted and write-only — only the last 4 characters are ever shown.
        </p>
        <Button size="sm" onClick={openCreate}><Plus className="h-4 w-4" /> Add Credential</Button>
      </div>

      {error ? (
        <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-surface-400">Loading credentials…</p>
      ) : (credentials ?? []).length === 0 ? (
        <Card><p className="py-8 text-center text-sm text-surface-400">No credentials yet.</p></Card>
      ) : (
        <div className="space-y-2">
          {(credentials ?? []).map((c) => {
            const res = results[c.id];
            return (
              <Card key={c.id} className="px-5 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
                      <KeyRound className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-surface-900 dark:text-surface-100">{c.name}</span>
                        <span className="shrink-0 rounded-full bg-surface-100 px-2 py-0.5 font-mono text-[10px] text-surface-500 dark:bg-surface-700">{c.type}</span>
                        <span className="shrink-0 rounded bg-surface-100 px-1.5 py-0.5 font-mono text-[10px] text-surface-500 dark:bg-surface-700">{c.hint || "no secret"}</span>
                      </div>
                      {(c.meta?.host || c.meta?.username) ? (
                        <p className="mt-0.5 truncate text-xs text-surface-400">
                          {[c.meta?.username, c.meta?.host].filter(Boolean).join(" @ ")}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 border-t border-surface-100 pt-3 dark:border-surface-700 sm:border-0 sm:pt-0">
                    <Button variant="outline" size="sm" isLoading={testing === c.id} onClick={() => handleTest(c)}>
                      <FlaskConical className="h-3.5 w-3.5" /> Test
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openReplace(c)}>
                      <RefreshCw className="h-3.5 w-3.5" /> Replace
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(c)} title="Delete">
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
                    {res.ok ? res.detail : `Failed: ${res.detail}`}
                  </p>
                ) : null}
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen} title={replacing ? `Replace secret — ${replacing.name}` : "Add Credential"}>
        <div className="space-y-4">
          {!replacing ? (
            <>
              <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="openai-prod" />
              <div>
                <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Type</label>
                <select value={ctype} onChange={(e) => { setCtype(e.target.value); setSecrets({}); }}
                  className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                  <option value="api_key">API key (LLM providers)</option>
                  <option value="basic">Username + password (IMAP mailboxes)</option>
                  <option value="oauth2">OAuth2 (Gmail / Outlook — M3)</option>
                </select>
              </div>
            </>
          ) : null}
          {ctype === "basic" ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input label="IMAP Host" value={host} onChange={(e) => setHost(e.target.value)} placeholder="imap.gmail.com" />
              <Input label="Username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="you@example.com" />
            </div>
          ) : null}
          {(SECRET_FIELDS[ctype] ?? []).map(({ key, label }) => (
            <Input key={key} label={label} type="password" value={secrets[key] ?? ""}
              onChange={(e) => setSecrets((s) => ({ ...s, [key]: e.target.value }))}
              placeholder={replacing ? "Leave blank to keep current" : "Paste secret"} />
          ))}
          {error ? (
            <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} isLoading={mut.create.isPending || mut.replaceSecret.isPending}>Save</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

import { motion } from "framer-motion";
import { Copy, Key, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Skeleton } from "../components/ui/Skeleton";
import { useAuth } from "../contexts/AuthContext";
import { cn } from "../lib/utils";

const API_BASE = "/api/v1";

interface ApiKeyItem {
  id: string;
  project_id: string;
  label: string;
  key_prefix: string;
  scopes: Record<string, unknown>;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

interface CreatedKey extends ApiKeyItem {
  raw_key: string;
}

export function ApiKeys() {
  const { projectId } = useParams<{ projectId: string }>();
  const { token } = useAuth();
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [label, setLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreatedKey | null>(null);

  function headers() {
    return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
  }

  async function loadKeys() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/api-keys?project_id=${projectId}`, { headers: headers() });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed" }))).detail);
      setKeys(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadKeys(); }, [projectId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) return;
    setCreating(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/api-keys`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ project_id: projectId, label: label.trim() }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: "Failed" }))).detail);
      const data: CreatedKey = await res.json();
      setCreatedKey(data);
      setLabel("");
      setShowCreate(false);
      loadKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/api-keys/${id}`, {
        method: "DELETE",
        headers: headers(),
      });
      if (!res.ok) throw new Error("Failed to revoke");
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke");
    }
  }

  function copyKey(raw: string) {
    navigator.clipboard.writeText(raw);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-surface-100">API Keys</h1>
          <p className="mt-1 text-sm text-surface-500">Manage API keys for RPA bot integration.</p>
        </div>
        <Button size="sm" onClick={() => { setShowCreate(true); setCreatedKey(null); }}>
          <Plus className="h-4 w-4" /> New Key
        </Button>
      </div>

      {error ? (
        <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
      ) : null}

      {createdKey ? (
        <Card className="space-y-3 border-emerald-300 dark:border-emerald-700">
          <h3 className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">Key Created</h3>
          <p className="text-xs text-surface-500">Copy this key now. You won't be able to see it again.</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded-lg bg-surface-100 px-3 py-2 text-xs font-mono break-all dark:bg-surface-700">{createdKey.raw_key}</code>
            <Button variant="ghost" size="sm" onClick={() => copyKey(createdKey.raw_key)}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setCreatedKey(null)}>Dismiss</Button>
        </Card>
      ) : null}

      {showCreate ? (
        <Card>
          <form onSubmit={handleCreate} className="space-y-3">
            <Input label="Key Label" placeholder="e.g. Invoice Bot" value={label} onChange={(e) => setLabel(e.target.value)} required id="key-label" />
            <div className="flex gap-2">
              <Button type="submit" size="sm" isLoading={creating}>Generate</Button>
              <Button variant="ghost" size="sm" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </form>
        </Card>
      ) : null}

      {loading ? (
        <div className="space-y-3">{[1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
      ) : keys.length === 0 ? (
        <Card><p className="py-8 text-center text-sm text-surface-400">No API keys yet.</p></Card>
      ) : (
        <div className="space-y-2">
          {keys.map((k) => (
            <motion.div key={k.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card className={cn("flex items-center gap-4 px-5 py-4", !k.is_active && "opacity-50")}>
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
                  <Key className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold text-surface-900 dark:text-surface-100">{k.label}</span>
                    <code className="shrink-0 rounded bg-surface-100 px-1.5 py-0.5 text-[10px] font-mono text-surface-500 dark:bg-surface-700">{k.key_prefix}...</code>
                    {!k.is_active ? (
                      <span className="shrink-0 rounded-full bg-accent-100 px-2 py-0.5 text-[10px] font-medium text-accent-600">revoked</span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-surface-400">Scopes: {Object.values(k.scopes).flat().join(", ")}</p>
                </div>
                {k.is_active ? (
                  <Button variant="ghost" size="sm" onClick={() => handleRevoke(k.id)} title="Revoke">
                    <Trash2 className="h-4 w-4 text-accent-400" />
                  </Button>
                ) : null}
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

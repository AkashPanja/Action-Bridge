import { Download, Play, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { api } from "../../lib/api";

interface OllamaModel {
  name: string;
  size: number;
  modified: string;
}

function formatSize(bytes: number) {
  if (!bytes) return "—";
  const gb = bytes / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

function isLocalhost(url: string) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host === "::1";
  } catch {
    return false;
  }
}

export function OllamaModelsPanel({ onUseModel }: { onUseModel: (model: string, baseUrl: string) => void }) {
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434");
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [pullName, setPullName] = useState("");
  const [pulling, setPulling] = useState(false);

  async function refresh(url: string = baseUrl) {
    setLoading(true);
    setMessage("");
    try {
      const res = await api.providers.ollamaModels(url);
      if (res.ok) {
        setModels(res.models);
        setMessage(res.detail);
      } else {
        setModels([]);
        setMessage(res.detail);
      }
    } catch (err) {
      setModels([]);
      setMessage(err instanceof Error ? err.message : "Failed to reach Ollama");
    }
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handlePull() {
    const name = pullName.trim();
    if (!name) return;
    setPulling(true);
    setMessage(`Pulling ${name} — this can take several minutes…`);
    try {
      const res = await api.providers.ollamaPull(baseUrl, name);
      setMessage(res.ok ? res.detail : `Pull failed: ${res.detail}`);
      if (res.ok) {
        setPullName("");
        await refresh();
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Pull failed");
    }
    setPulling(false);
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="http://localhost:11434"
          className="min-w-0 flex-1 rounded-xl border border-transparent bg-surface-100 px-4 py-2.5 font-mono text-xs dark:bg-surface-800" />
        <Button variant="outline" size="sm" onClick={() => refresh()} isLoading={loading}>
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>
      {message ? <p className="mt-2 text-xs text-surface-400">{message}</p> : null}

      {models.length > 0 ? (
        <div className="mt-3 space-y-2">
          {models.map((m) => (
            <Card key={m.name} className="px-4 py-3">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs font-semibold text-surface-900 dark:text-surface-100">{m.name}</p>
                  <p className="text-[11px] text-surface-400">{formatSize(m.size)}{m.modified ? ` · ${m.modified}` : ""}</p>
                </div>
                <Button variant="outline" size="sm" onClick={() => onUseModel(m.name, baseUrl)}>
                  <Play className="h-3.5 w-3.5" /> Use
                </Button>
              </div>
            </Card>
          ))}
        </div>
      ) : null}

      <div className="mt-3 flex items-center gap-2">
        <input value={pullName} onChange={(e) => setPullName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handlePull(); }}
          placeholder="Pull a model, e.g. gemma3:4b"
          className="min-w-0 flex-1 rounded-xl border border-transparent bg-surface-100 px-4 py-2.5 font-mono text-xs dark:bg-surface-800" />
        <Button size="sm" onClick={handlePull} isLoading={pulling} disabled={!pullName.trim()}>
          <Download className="h-3.5 w-3.5" /> Pull
        </Button>
      </div>
      <p className="mt-1 text-[11px] text-surface-400">
        Any model tag from the Ollama library works — it downloads into Ollama, then appears above.
        {isLocalhost(baseUrl) ? "" : " Remote servers are treated as non-local (cloud-gated)."}
      </p>
    </div>
  );
}

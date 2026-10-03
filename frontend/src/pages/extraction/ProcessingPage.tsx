import { useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { useProcessing, useUpdateProcessing } from "../../hooks/useExtraction";

export function ProcessingPage() {
  const { data, isLoading } = useProcessing();
  const update = useUpdateProcessing();
  const [form, setForm] = useState({ cpu_workers: 4, max_jobs_in_flight: 8, default_retries: 3, default_timeout_s: 120, paused: false, auto_approve_threshold: 0.92 });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (data) {
      setForm({
        cpu_workers: data.cpu_workers,
        max_jobs_in_flight: data.max_jobs_in_flight,
        default_retries: data.default_retries,
        default_timeout_s: data.default_timeout_s,
        paused: data.paused,
        auto_approve_threshold: data.auto_approve_threshold ?? 0.92,
      });
    }
  }, [data]);

  async function handleSave() {
    setError("");
    setSaved(false);
    try {
      await update.mutateAsync(form);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  const set = (k: keyof typeof form, v: number | boolean) =>
    setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="space-y-4">
      <p className="text-sm text-surface-500">
        Applies immediately — no restart needed. Per-provider LLM concurrency lives on each provider.
      </p>
      <Card className="space-y-4 p-5">
        {isLoading ? (
          <p className="text-sm text-surface-400">Loading…</p>
        ) : (
          <>
            <label className="flex items-center gap-2 text-sm font-medium text-surface-700 dark:text-surface-300">
              <input type="checkbox" checked={form.paused} onChange={(e) => set("paused", e.target.checked)}
                className="rounded border-surface-300 text-brand-600 focus:ring-brand-500" />
              Pause all processing (workers idle, queue kept)
            </label>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input label="CPU workers (parsing, rendering, download)" type="number" min={1} max={32}
                value={form.cpu_workers} onChange={(e) => set("cpu_workers", parseInt(e.target.value) || 1)} />
              <Input label="Max jobs in flight" type="number" min={1} max={128}
                value={form.max_jobs_in_flight} onChange={(e) => set("max_jobs_in_flight", parseInt(e.target.value) || 1)} />
              <Input label="Default retries" type="number" min={0} max={10}
                value={form.default_retries} onChange={(e) => set("default_retries", parseInt(e.target.value) || 0)} />
              <Input label="Default timeout (seconds)" type="number" min={5} max={3600}
                value={form.default_timeout_s} onChange={(e) => set("default_timeout_s", parseInt(e.target.value) || 5)} />
              <Input label="Auto-approve at/above score (0 disables)" type="number" min={0} max={1} step={0.01}
                value={form.auto_approve_threshold} onChange={(e) => set("auto_approve_threshold", parseFloat(e.target.value) || 0)} />
            </div>
            <p className="-mt-2 text-xs text-surface-400">
              Extractions where every field scores at or above this are approved without human review.
            </p>
            {error ? (
              <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
            ) : null}
            {saved ? (
              <p className="rounded-xl bg-emerald-50 px-4 py-2 text-sm text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-300">
                Settings saved and active.
              </p>
            ) : null}
            <Button onClick={handleSave} isLoading={update.isPending}>Save Processing Settings</Button>
          </>
        )}
      </Card>
    </div>
  );
}

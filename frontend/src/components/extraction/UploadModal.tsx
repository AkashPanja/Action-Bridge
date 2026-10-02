import { UploadCloud } from "lucide-react";
import { useState } from "react";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useProfiles } from "../../hooks/useExtraction";
import { useDocumentTypes } from "../../hooks/useDocumentTypes";
import { api } from "../../lib/api";

export function UploadModal({
  projectId, open, onClose,
}: {
  projectId: string; open: boolean; onClose: () => void;
}) {
  const { data: profiles } = useProfiles(projectId);
  const { data: docTypes } = useDocumentTypes(projectId);
  const [mode, setMode] = useState<"profile" | "type">("profile");
  const [profileId, setProfileId] = useState("");
  const [typeId, setTypeId] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ job_id: string; submission_id: string } | null>(null);

  async function handleSubmit() {
    setError("");
    if (!files || files.length === 0) {
      setError("Choose at least one file");
      return;
    }
    if (mode === "profile" && !profileId) {
      setError("Pick an extraction profile");
      return;
    }
    if (mode === "type" && !typeId) {
      setError("Pick a document type");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      if (mode === "profile") fd.append("profile_id", profileId);
      else fd.append("document_type_id", typeId);
      if (note.trim()) fd.append("note", note.trim());
      Array.from(files).forEach((f) => fd.append("files", f));
      const res = await api.extract.upload(projectId, fd);
      setDone({ job_id: res.job_id, submission_id: res.submission_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
    setBusy(false);
  }

  function handleClose() {
    setDone(null);
    setError("");
    setFiles(null);
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); }}
      title="Upload documents for extraction"
      description="Files are queued for AI extraction. Results land in this inbox for review.">
      {done ? (
        <div className="space-y-4">
          <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300">
            Uploaded. Job <span className="font-mono">{done.job_id.slice(0, 8)}…</span> is
            processing — track it in the <strong>Jobs</strong> tab; documents appear here once done.
          </p>
          <div className="flex justify-end">
            <Button onClick={handleClose}>Done</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex gap-2">
            {(["profile", "type"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${mode === m ? "bg-brand-600 text-white" : "bg-surface-100 text-surface-500 dark:bg-surface-700"}`}>
                {m === "profile" ? "Use a profile" : "Use a document type"}
              </button>
            ))}
          </div>
          {mode === "profile" ? (
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Extraction profile</label>
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">Select a profile…</option>
                {(profiles ?? []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.mode})</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Document type</label>
              <select value={typeId} onChange={(e) => setTypeId(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800">
                <option value="">Select a type…</option>
                {(docTypes ?? []).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Files</label>
            <input type="file" multiple onChange={(e) => setFiles(e.target.files)}
              className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800" />
            <p className="mt-1 text-xs text-surface-400">PDF, images, Word, Excel, CSV, TXT. Max 25 MB each.</p>
          </div>
          <div>
            <label className="text-sm font-medium text-surface-700 dark:text-surface-300">Note (optional)</label>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Batch reference…"
              className="mt-1.5 w-full rounded-xl border border-transparent bg-surface-100 px-4 py-3 text-sm dark:bg-surface-800" />
          </div>
          {error ? (
            <p className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleClose}>Cancel</Button>
            <Button onClick={handleSubmit} isLoading={busy}>
              <UploadCloud className="h-4 w-4" /> Upload & Extract
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

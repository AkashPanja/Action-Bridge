import { Download, Eye, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useSubmission } from "../../hooks/useExtraction";
import { api } from "../../lib/api";
import type { SubmissionFile } from "../../types/extraction";
import { cn } from "../../lib/utils";

const FILE_STATUS_STYLES: Record<string, string> = {
  extracted: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  skipped: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  duplicate: "bg-surface-100 text-surface-500 dark:bg-surface-700 dark:text-surface-300",
  failed: "bg-accent-100 text-accent-600 dark:bg-accent-900/30 dark:text-accent-400",
  pending: "bg-surface-100 text-surface-500 dark:bg-surface-700",
  processing: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
};

function isPreviewable(mime: string, filename: string) {
  if (mime === "application/pdf" || filename.toLowerCase().endsWith(".pdf")) return "pdf";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("text/") || /\.(txt|csv|md)$/i.test(filename)) return "text";
  return null;
}

export function SourceFilesPanel({ submissionId }: { submissionId: string }) {
  const { data: submission, isLoading } = useSubmission(submissionId);
  const [preview, setPreview] = useState<{ file: SubmissionFile; url: string; kind: string } | null>(null);
  const [previewText, setPreviewText] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);

  async function openPreview(file: SubmissionFile) {
    const kind = isPreviewable(file.mime, file.filename);
    if (!kind) {
      await download(file);
      return;
    }
    setLoadingPreview(true);
    try {
      const url = await api.submissions.fileBlob(submissionId, file.id);
      if (kind === "text") {
        const text = await (await fetch(url)).text();
        setPreviewText(text.slice(0, 20000));
      }
      setPreview({ file, url, kind });
    } catch {
      // toast-less fallback: nothing to show
    }
    setLoadingPreview(false);
  }

  function closePreview() {
    if (preview) URL.revokeObjectURL(preview.url);
    setPreview(null);
    setPreviewText("");
  }

  async function download(file: SubmissionFile) {
    try {
      const url = await api.submissions.fileBlob(submissionId, file.id);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch {
      // ignore
    }
  }

  if (isLoading) return <p className="py-4 text-center text-sm text-surface-400">Loading source files…</p>;
  if (!submission) return null;

  return (
    <div className="space-y-2">
      {submission.email_meta ? (
        <div className="rounded-xl bg-surface-100/70 px-3 py-2 text-xs text-surface-500 dark:bg-surface-800 dark:text-surface-400">
          <p className="truncate font-medium text-surface-700 dark:text-surface-200">
            {String(submission.email_meta.subject ?? "(no subject)")}
          </p>
          <p className="truncate">From: {String(submission.email_meta.from ?? "—")}</p>
        </div>
      ) : null}
      {(submission.files ?? []).map((f) => (
        <div key={f.id} className="flex items-center gap-2 rounded-lg bg-surface-50 px-3 py-2 dark:bg-surface-800">
          <FileText className="h-4 w-4 shrink-0 text-surface-400" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-surface-700 dark:text-surface-200">{f.filename}</p>
            <p className="text-[10px] text-surface-400">
              <span className={cn("rounded-full px-1.5 py-px font-medium", FILE_STATUS_STYLES[f.status] ?? "")}>
                {f.status}
              </span>
              {f.skip_reason ? ` · ${f.skip_reason}` : ""}
            </p>
          </div>
          <button onClick={() => openPreview(f)} disabled={loadingPreview} title="Preview"
            className="shrink-0 rounded-lg p-1.5 text-surface-400 hover:bg-surface-200 hover:text-surface-600 dark:hover:bg-surface-700">
            <Eye className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => download(f)} title="Download"
            className="shrink-0 rounded-lg p-1.5 text-surface-400 hover:bg-surface-200 hover:text-surface-600 dark:hover:bg-surface-700">
            <Download className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}

      <Dialog open={!!preview} onOpenChange={(o) => { if (!o) closePreview(); }}
        title={preview?.file.filename ?? "Preview"} className="max-w-3xl">
        {preview?.kind === "pdf" ? (
          <iframe src={preview.url} title="PDF preview" className="h-[70vh] w-full rounded-xl border border-surface-200 dark:border-surface-700" />
        ) : preview?.kind === "image" ? (
          <img src={preview.url} alt={preview.file.filename} className="max-h-[70vh] w-full rounded-xl object-contain" />
        ) : (
          <pre className="max-h-[70vh] overflow-auto rounded-xl bg-surface-100 p-4 font-mono text-xs dark:bg-surface-900">{previewText}</pre>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => preview && download(preview.file)}>
            <Download className="h-3.5 w-3.5" /> Download
          </Button>
          <Button variant="outline" size="sm" onClick={closePreview}>
            <X className="h-3.5 w-3.5" /> Close
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

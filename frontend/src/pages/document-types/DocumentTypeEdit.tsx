import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { SchemaAdvancedEditor } from "../../components/schema/SchemaAdvancedEditor";
import { SchemaBuilder } from "../../components/schema/SchemaBuilder";
import { ValidationRulesDialog } from "../../components/schema/ValidationRulesDialog";
import { useUpdateDocumentType } from "../../hooks/useDocumentTypes";

const EMPTY_SCHEMA: Record<string, unknown> = {
  type: "object",
  title: "Document",
  required: [],
  properties: {},
};

interface Props {
  projectId: string;
  docType: { id: string; name: string; schema_definition: Record<string, unknown>; validation_rules?: Record<string, unknown> | null; confidence_threshold?: number | null } | null;
  onClose: () => void;
}

export function DocumentTypeEditDialog({ projectId, docType, onClose }: Props) {
  const [name, setName] = useState(docType?.name ?? "");
  const [threshold, setThreshold] = useState(
    docType?.confidence_threshold != null ? String(docType.confidence_threshold) : "0.95",
  );
  const [tab, setTab] = useState<"visual" | "advanced">("visual");
  const [schema, setSchema] = useState<Record<string, unknown>>(docType?.schema_definition ?? EMPTY_SCHEMA);
  const [jsonText, setJsonText] = useState(docType ? JSON.stringify(docType.schema_definition, null, 2) : "");
  const [error, setError] = useState("");
  const [rulesOpen, setRulesOpen] = useState(false);
  const updateDocType = useUpdateDocumentType(projectId);

  useEffect(() => {
    if (docType) {
      setName(docType.name);
      setThreshold(docType.confidence_threshold != null ? String(docType.confidence_threshold) : "0.95");
      setSchema(docType.schema_definition);
      setJsonText(JSON.stringify(docType.schema_definition, null, 2));
      setError("");
    }
  }, [docType]);

  function handleVisualChange(newSchema: Record<string, unknown>) {
    setSchema(newSchema);
    setJsonText(JSON.stringify(newSchema, null, 2));
    setError("");
  }

  function handleAdvancedChange(text: string) {
    setJsonText(text);
  }

  function handleValidJson(json: Record<string, unknown>) {
    setSchema(json);
    setError("");
  }

  function handleTabChange(newTab: "visual" | "advanced") {
    if (newTab === "advanced") {
      setJsonText(JSON.stringify(schema, null, 2));
    } else {
      try {
        const parsed = JSON.parse(jsonText);
        if (!parsed.type || !parsed.properties) {
          setError("Schema must have 'type' and 'properties'");
          return;
        }
        setSchema(parsed);
        setError("");
      } catch {
        setError("Invalid JSON. Fix errors before switching to Visual.");
        return;
      }
    }
    setTab(newTab);
    setError("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!name.trim()) return;

    let finalSchema = schema;
    if (tab === "advanced") {
      try {
        finalSchema = JSON.parse(jsonText);
      } catch {
        setError("Invalid JSON. Please check your syntax.");
        return;
      }
    }

    if (!finalSchema.type || !finalSchema.properties) {
      setError("Schema must have 'type' and 'properties' fields.");
      return;
    }

    try {
      const t = parseFloat(threshold);
      if (Number.isNaN(t) || t < 0 || t > 1) {
        setError("Confidence threshold must be between 0 and 1.");
        return;
      }
      await updateDocType.mutateAsync({
        typeId: docType!.id,
        data: {
          name: name.trim(),
          schema_definition: finalSchema,
          confidence_threshold: t,
        },
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
    }
  }

  return (
    <>
      <Dialog open={!!docType} onOpenChange={(open) => { if (!open) onClose(); }} title="Edit Document Type" description="Update the name and schema definition.">
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input label="Document Type Name" placeholder="e.g. Invoice" value={name} onChange={(e) => setName(e.target.value)} required id="edit-doc-type-name" />
          <Input label="Required confidence to auto-approve (mandatory fields must score ≥ this)" type="number" min="0" max="1" step="0.01" value={threshold} onChange={(e) => setThreshold(e.target.value)} id="edit-doc-type-threshold" />

          <div className="flex gap-1 rounded-lg bg-surface-100 p-1 dark:bg-surface-700">
            <button type="button" onClick={() => handleTabChange("visual")} className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-all ${tab === "visual" ? "bg-white text-surface-900 shadow-sm dark:bg-surface-600 dark:text-surface-100" : "text-surface-500 hover:text-surface-700 dark:text-surface-400"}`}>Visual Builder</button>
            <button type="button" onClick={() => handleTabChange("advanced")} className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-all ${tab === "advanced" ? "bg-white text-surface-900 shadow-sm dark:bg-surface-600 dark:text-surface-100" : "text-surface-500 hover:text-surface-700 dark:text-surface-400"}`}>Advanced JSON</button>
          </div>

          {tab === "visual" ? (
            <SchemaBuilder schema={schema} onChange={handleVisualChange} />
          ) : (
            <SchemaAdvancedEditor value={jsonText} onChange={handleAdvancedChange} onValidJson={handleValidJson} />
          )}

          {error ? <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">{error}</motion.p> : null}

          <div className="flex justify-between gap-3 pt-2">
            <Button type="button" variant="outline" onClick={() => setRulesOpen(true)}>
              Validation Rules
            </Button>
            <div className="flex gap-3">
              <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
              <Button type="submit" isLoading={updateDocType.isPending}>Save Changes</Button>
            </div>
          </div>
        </form>
      </Dialog>
      {docType ? (
        <ValidationRulesDialog
          projectId={projectId}
          docType={docType}
          open={rulesOpen}
          onOpenChange={setRulesOpen}
        />
      ) : null}
    </>
  );
}

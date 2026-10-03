import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { SchemaAdvancedEditor } from "../../components/schema/SchemaAdvancedEditor";
import { SchemaBuilder } from "../../components/schema/SchemaBuilder";
import { useCreateDocumentType } from "../../hooks/useDocumentTypes";

const INVOICE_SCHEMA: Record<string, unknown> = {
  type: "object",
  title: "Invoice",
  required: ["invoice_number", "total_amount"],
  properties: {
    invoice_number: { type: "string", title: "Invoice #" },
    total_amount: { type: "number", title: "Total Amount" },
    currency: { type: "string", title: "Currency", enum: ["USD", "EUR", "GBP"] },
    invoice_date: { type: "string", format: "date", title: "Date" },
  },
};

interface Props {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentTypeCreateDialog({ projectId, open, onOpenChange }: Props) {
  const [name, setName] = useState("");
  const [tab, setTab] = useState<"visual" | "advanced">("visual");
  const [schema, setSchema] = useState<Record<string, unknown>>(INVOICE_SCHEMA);
  const [jsonText, setJsonText] = useState(JSON.stringify(INVOICE_SCHEMA, null, 2));
  const [error, setError] = useState("");
  const createDocType = useCreateDocumentType(projectId);

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
      } catch (e) {
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
      await createDocType.mutateAsync({
        name: name.trim(),
        schema_definition: finalSchema,
      });
      setName("");
      setSchema(INVOICE_SCHEMA);
      setJsonText(JSON.stringify(INVOICE_SCHEMA, null, 2));
      setTab("visual");
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Create Document Type"
      description="Define the fields and schema for this document type."
      className="sm:max-w-3xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Document Type Name"
          placeholder="e.g. Invoice, Purchase Order, Contract"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          id="doc-type-name"
        />

        <div className="flex gap-1 rounded-lg bg-surface-100 p-1 dark:bg-surface-700">
          <button
            type="button"
            onClick={() => handleTabChange("visual")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
              tab === "visual"
                ? "bg-white text-surface-900 shadow-sm dark:bg-surface-600 dark:text-surface-100"
                : "text-surface-500 hover:text-surface-700 dark:text-surface-400"
            }`}
          >
            Visual Builder
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("advanced")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-all ${
              tab === "advanced"
                ? "bg-white text-surface-900 shadow-sm dark:bg-surface-600 dark:text-surface-100"
                : "text-surface-500 hover:text-surface-700 dark:text-surface-400"
            }`}
          >
            Advanced JSON
          </button>
        </div>

        {tab === "visual" ? (
          <SchemaBuilder schema={schema} onChange={handleVisualChange} />
        ) : (
          <SchemaAdvancedEditor
            value={jsonText}
            onChange={handleAdvancedChange}
            onValidJson={handleValidJson}
          />
        )}

        {error ? <p className="text-xs text-accent-500">{error}</p> : null}

        <p className="text-xs text-surface-400">Validation rules can be added after creating the document type.</p>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" isLoading={createDocType.isPending}>
            Create
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

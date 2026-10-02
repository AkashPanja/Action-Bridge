import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/ui/Button";
import { fieldsToSchema, schemaToFields, type FieldDefinition } from "./types";

interface Props {
  schema: Record<string, unknown>;
  onChange: (schema: Record<string, unknown>) => void;
  readOnly?: boolean;
}

function emptyField(): FieldDefinition {
  return { key: "", type: "string", title: "", required: false, enumValues: [] };
}

export function SchemaBuilder({ schema, onChange, readOnly }: Props) {
  const [fields, setFields] = useState<FieldDefinition[]>(() => {
    const parsed = schemaToFields(schema);
    return parsed.length > 0 ? parsed : [emptyField()];
  });

  const generatedSchema = useMemo(() => fieldsToSchema(fields), [fields]);

  useEffect(() => {
    onChange(generatedSchema);
  }, [generatedSchema]);

  function updateField(index: number, partial: Partial<FieldDefinition>) {
    setFields((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...partial };
      return next;
    });
  }

  function removeField(index: number) {
    setFields((prev) => prev.filter((_, i) => i !== index));
  }

  function moveField(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= fields.length) return;
    setFields((prev) => {
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function addField() {
    setFields((prev) => [...prev, emptyField()]);
  }

  function updateColumn(fieldIndex: number, colIndex: number, partial: Partial<FieldDefinition>) {
    setFields((prev) => {
      const next = [...prev];
      const field = { ...next[fieldIndex] };
      const columns = [...(field.columns ?? [])];
      columns[colIndex] = { ...columns[colIndex], ...partial };
      field.columns = columns;
      next[fieldIndex] = field;
      return next;
    });
  }

  function removeColumn(fieldIndex: number, colIndex: number) {
    setFields((prev) => {
      const next = [...prev];
      const field = { ...next[fieldIndex] };
      field.columns = (field.columns ?? []).filter((_, i) => i !== colIndex);
      next[fieldIndex] = field;
      return next;
    });
  }

  function moveColumn(fieldIndex: number, colIndex: number, direction: -1 | 1) {
    setFields((prev) => {
      const next = [...prev];
      const field = { ...next[fieldIndex] };
      const columns = [...(field.columns ?? [])];
      const target = colIndex + direction;
      if (target < 0 || target >= columns.length) return prev;
      [columns[colIndex], columns[target]] = [columns[target], columns[colIndex]];
      field.columns = columns;
      next[fieldIndex] = field;
      return next;
    });
  }

  function addColumn(fieldIndex: number) {
    setFields((prev) => {
      const next = [...prev];
      const field = { ...next[fieldIndex] };
      field.columns = [...(field.columns ?? []), { key: "", type: "string", title: "", required: false, enumValues: [] }];
      next[fieldIndex] = field;
      return next;
    });
  }

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-surface-200 dark:border-surface-600 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="bg-surface-50 dark:bg-surface-800">
              {!readOnly ? <th className="w-8 px-2 py-2"></th> : null}
              <th className="px-2 py-2 text-left text-xs font-medium text-surface-500">Field Name</th>
              <th className="w-24 px-2 py-2 text-left text-xs font-medium text-surface-500">Type</th>
              <th className="w-16 px-2 py-2 text-center text-xs font-medium text-surface-500">Req.</th>
              <th className="px-2 py-2 text-left text-xs font-medium text-surface-500">Details</th>
              {!readOnly ? <th className="w-28 px-2 py-2 text-center text-xs font-medium text-surface-500">Actions</th> : null}
            </tr>
          </thead>
          <tbody>
            {fields.map((field, i) => (
              <tr key={i} className="border-t border-surface-100 dark:border-surface-700">
                {!readOnly ? (
                  <td className="px-2 py-2 text-surface-300">
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                    </svg>
                  </td>
                ) : null}
                  <td className="px-2 py-2">
                    {readOnly ? (
                      <span className="text-sm font-medium text-surface-700 dark:text-surface-200">{field.key}</span>
                    ) : (
                      <input
                        value={field.key}
                        onChange={(e) => updateField(i, { key: e.target.value })}
                        placeholder="field_name"
                        className="w-full rounded-lg border border-surface-200 bg-white px-2.5 py-1.5 text-sm focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                      />
                    )}
                  </td>
                  <td className="px-2 py-2">
                    {readOnly ? (
                      <span className="text-sm text-surface-600 dark:text-surface-300">{field.type}</span>
                    ) : (
                      <select
                        value={field.type}
                        onChange={(e) => updateField(i, { type: e.target.value as FieldDefinition["type"] })}
                        className="w-full rounded-lg border border-surface-200 bg-white px-2 py-1.5 text-sm focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                      >
                        <option value="string">string</option>
                        <option value="number">number</option>
                        <option value="boolean">boolean</option>
                        <option value="date">date</option>
                        <option value="enum">enum</option>
                        <option value="table">table</option>
                      </select>
                    )}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {readOnly ? (
                      <span className="text-sm text-surface-600 dark:text-surface-300">{field.required ? "Yes" : "No"}</span>
                    ) : (
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) => updateField(i, { required: e.target.checked })}
                        className="rounded border-surface-300 text-brand-500 focus:ring-brand-500"
                      />
                    )}
                  </td>
                  <td className="px-2 py-2">
                    {field.type === "enum" ? (
                      readOnly ? (
                        <span className="text-xs text-surface-600 dark:text-surface-300">{field.enumValues.join(", ")}</span>
                      ) : (
                        <input
                          value={field.enumValues.join(", ")}
                          onChange={(e) => updateField(i, { enumValues: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                          placeholder="val1, val2, ..."
                          className="w-full rounded-lg border border-surface-200 bg-white px-2 py-1.5 text-xs focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                        />
                      )
                    ) : field.type === "table" ? (
                      <span className="text-xs text-surface-400">{field.columns?.length ?? 0} columns</span>
                    ) : null}
                  </td>
                  <td className="px-2 py-2">
                    {!readOnly ? (
                      <div className="flex items-center justify-center gap-0.5">
                        <button type="button" onClick={() => moveField(i, -1)} disabled={i === 0} className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600 disabled:opacity-30 dark:hover:bg-surface-700">
                          <ArrowUp className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => moveField(i, 1)} disabled={i === fields.length - 1} className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600 disabled:opacity-30 dark:hover:bg-surface-700">
                          <ArrowDown className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => removeField(i)} disabled={fields.length === 1} className="rounded p-1 text-accent-400 hover:bg-accent-50 hover:text-accent-600 disabled:opacity-30 dark:hover:bg-accent-900/20">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : null}
                  </td>
              </tr>
            ))}
            {fields.map((field, i) =>
              field.type === "table" ? (
                <tr key={`cols-${i}`}>
                  <td colSpan={readOnly ? 4 : 6} className="px-6 pb-3 pt-0">
                    <div className="rounded-lg border border-brand-200 bg-brand-50/30 p-3 dark:border-brand-800 dark:bg-brand-900/10">
                      <div className="mb-2 text-xs font-semibold text-brand-600 dark:text-brand-400">Columns for "{field.key || "untitled"}"</div>
                      <table className="w-full min-w-[440px] text-xs">
                        <thead>
                          <tr className="border-b border-brand-200 dark:border-brand-800">
                            <th className="px-2 py-1 text-left font-medium text-brand-600 dark:text-brand-400">Column Name</th>
                            <th className="w-20 px-2 py-1 text-left font-medium text-brand-600 dark:text-brand-400">Type</th>
                            <th className="w-12 px-2 py-1 text-center font-medium text-brand-600 dark:text-brand-400">Req.</th>
                            <th className="px-2 py-1 text-left font-medium text-brand-600 dark:text-brand-400">Enum Values</th>
                            <th className="w-16 px-2 py-1 text-center font-medium text-brand-600 dark:text-brand-400"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {(field.columns ?? []).map((col, ci) => (
                            <tr key={ci} className="border-b border-brand-100 dark:border-brand-800/50">
                              <td className="px-2 py-1">
                                {readOnly ? (
                                  <span className="text-xs font-medium text-surface-700 dark:text-surface-200">{col.key}</span>
                                ) : (
                                  <input
                                    value={col.key}
                                    onChange={(e) => updateColumn(i, ci, { key: e.target.value })}
                                    placeholder="column_name"
                                    className="w-full rounded border border-brand-200 bg-white px-2 py-1 text-xs focus:border-brand-500 focus:outline-none dark:border-brand-700 dark:bg-surface-800 dark:text-surface-100"
                                  />
                                )}
                              </td>
                              <td className="px-2 py-1">
                                {readOnly ? (
                                  <span className="text-xs text-surface-600 dark:text-surface-300">{col.type}</span>
                                ) : (
                                  <select
                                    value={col.type}
                                    onChange={(e) => updateColumn(i, ci, { type: e.target.value as FieldDefinition["type"] })}
                                    className="w-full rounded border border-brand-200 bg-white px-1.5 py-1 text-xs focus:border-brand-500 focus:outline-none dark:border-brand-700 dark:bg-surface-800 dark:text-surface-100"
                                  >
                                    <option value="string">string</option>
                                    <option value="number">number</option>
                                    <option value="boolean">boolean</option>
                                    <option value="date">date</option>
                                    <option value="enum">enum</option>
                                  </select>
                                )}
                              </td>
                              <td className="px-2 py-1 text-center">
                                {readOnly ? (
                                  <span className="text-xs text-surface-600">{col.required ? "Yes" : "No"}</span>
                                ) : (
                                  <input
                                    type="checkbox"
                                    checked={col.required}
                                    onChange={(e) => updateColumn(i, ci, { required: e.target.checked })}
                                    className="rounded border-brand-300 text-brand-500 focus:ring-brand-500"
                                  />
                                )}
                              </td>
                              <td className="px-2 py-1">
                                {col.type === "enum" ? (
                                  readOnly ? (
                                    <span className="text-xs text-surface-600">{col.enumValues.join(", ")}</span>
                                  ) : (
                                    <input
                                      value={col.enumValues.join(", ")}
                                      onChange={(e) => updateColumn(i, ci, { enumValues: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                                      placeholder="val1, val2, ..."
                                      className="w-full rounded border border-brand-200 bg-white px-2 py-1 text-xs focus:border-brand-500 focus:outline-none dark:border-brand-700 dark:bg-surface-800 dark:text-surface-100"
                                    />
                                  )
                                ) : null}
                              </td>
                              <td className="px-2 py-1">
                                {!readOnly ? (
                                  <div className="flex items-center justify-center gap-0.5">
                                    <button type="button" onClick={() => moveColumn(i, ci, -1)} disabled={ci === 0} className="rounded p-0.5 text-brand-400 hover:bg-brand-100 hover:text-brand-600 disabled:opacity-30 dark:hover:bg-brand-900/30">
                                      <ArrowUp className="h-3 w-3" />
                                    </button>
                                    <button type="button" onClick={() => moveColumn(i, ci, 1)} disabled={ci === (field.columns ?? []).length - 1} className="rounded p-0.5 text-brand-400 hover:bg-brand-100 hover:text-brand-600 disabled:opacity-30 dark:hover:bg-brand-900/30">
                                      <ArrowDown className="h-3 w-3" />
                                    </button>
                                    <button type="button" onClick={() => removeColumn(i, ci)} disabled={(field.columns ?? []).length === 1} className="rounded p-0.5 text-accent-400 hover:bg-accent-50 hover:text-accent-600 disabled:opacity-30 dark:hover:bg-accent-900/20">
                                      <Trash2 className="h-3 w-3" />
                                    </button>
                                  </div>
                                ) : null}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {!readOnly ? (
                        <button
                          type="button"
                          onClick={() => addColumn(i)}
                          className="mt-2 flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
                        >
                          <Plus className="h-3 w-3" /> Add Column
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ) : null
            )}
          </tbody>
        </table>
      </div>

      {!readOnly ? (
        <Button type="button" variant="ghost" size="sm" onClick={addField} className="w-full">
          <Plus className="h-4 w-4" /> Add Field
        </Button>
      ) : null}
    </div>
  );
}

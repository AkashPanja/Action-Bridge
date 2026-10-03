import { Plus, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useRegexPatterns } from "../../hooks/useRegexPatterns";
import { useUpdateDocumentType } from "../../hooks/useDocumentTypes";
import { schemaToFields, type FieldDefinition } from "./types";
import { RegexBuilder } from "./RegexBuilder";

interface Props {
  projectId: string;
  docType: { id: string; name: string; schema_definition: Record<string, unknown>; validation_rules?: Record<string, unknown> | null } | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const RULE_LABELS: Record<string, string> = {
  confidence_min: "Confidence min",
  min_length: "Min length",
  max_length: "Max length",
  min_value: "Min value",
  max_value: "Max value",
};

const RULE_DESCRIPTIONS: Record<string, string> = {
  confidence_min: "0–100",
  min_length: "e.g. 1",
  max_length: "e.g. 255",
  min_value: "e.g. 0",
  max_value: "e.g. 10000",
};

const BUILT_IN_PATTERNS: Record<string, { pattern: string; flags: string; label: string }> = {
  istext: { pattern: "^[a-zA-Z\\s]+$", flags: "", label: "Is Text" },
  isonlytext: { pattern: "^[a-zA-Z]+$", flags: "", label: "Is Only Text" },
  isnumber: { pattern: "^\\-?\\d+(\\.\\d+)*$", flags: "", label: "Is Number" },
  isonlynumber: { pattern: "^\\-?\\d+(\\.\\d+)?$", flags: "", label: "Is Only Number" },
  isdecimal: { pattern: "^\\-?\\d+\\.\\d+$", flags: "", label: "Is Decimal" },
  issymbol: { pattern: "^[^a-zA-Z0-9\\s]+$", flags: "", label: "Is Symbol" },
  isemailid: { pattern: "^[\\w.-]+@[\\w.-]+\\.\\w{2,}$", flags: "", label: "Email Address" },
  isip: { pattern: "^(?:\\d{1,3}\\.){3}\\d{1,3}$", flags: "", label: "IP Address" },
};

function getApplicableRules(fieldType: FieldDefinition["type"]): string[] {
  const rules: string[] = [];
  if (fieldType === "string" || fieldType === "date" || fieldType === "enum") {
    rules.push("min_length", "max_length");
  }
  if (fieldType === "number") {
    rules.push("min_value", "max_value");
  }
  return rules;
}

function PatternEntryForm({
  onAdd,
  onCancel,
}: {
  onAdd: (entry: { id?: string; pattern?: string; negate?: boolean }) => void;
  onCancel: () => void;
}) {
  const { data: namedPatterns } = useRegexPatterns();
  const [mode, setMode] = useState<"builtin" | "saved" | "custom">("builtin");
  const [selectedId, setSelectedId] = useState("");
  const [customPattern, setCustomPattern] = useState("");
  const [customFlags, setCustomFlags] = useState("");
  const [negate, setNegate] = useState(false);
  const [search, setSearch] = useState("");

  const filteredSaved = useMemo(() => {
    if (!namedPatterns) return [];
    if (!search) return namedPatterns;
    const q = search.toLowerCase();
    return namedPatterns.filter(
      (p) => p.name.toLowerCase().includes(q) || p.pattern.includes(q),
    );
  }, [namedPatterns, search]);

  const filteredBuiltin = useMemo(() => {
    if (!search) return Object.entries(BUILT_IN_PATTERNS);
    const q = search.toLowerCase();
    return Object.entries(BUILT_IN_PATTERNS).filter(
      ([key, p]) => key.toLowerCase().includes(q) || p.label.toLowerCase().includes(q) || p.pattern.includes(q),
    );
  }, [search]);

  function handleAdd() {
    if (mode === "builtin" && selectedId) {
      const builtin = BUILT_IN_PATTERNS[selectedId];
      if (builtin) {
        onAdd({ pattern: builtin.pattern, negate });
        return;
      }
    }
    if (mode === "saved" && selectedId) {
      onAdd({ id: selectedId, negate });
    } else if (mode === "custom" && customPattern) {
      onAdd({ pattern: customPattern, negate });
    }
  }

  return (
    <div className="rounded-xl border border-surface-200 bg-white p-4 shadow-lg dark:border-surface-600 dark:bg-surface-800">
      <div className="mb-3 flex gap-2">
        <button
          type="button"
          onClick={() => setMode("builtin")}
          className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
            mode === "builtin"
              ? "bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
              : "bg-surface-100 text-surface-500 hover:text-surface-700 dark:bg-surface-700 dark:text-surface-400"
          }`}
        >
          Built-in
        </button>
        <button
          type="button"
          onClick={() => setMode("saved")}
          className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
            mode === "saved"
              ? "bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
              : "bg-surface-100 text-surface-500 hover:text-surface-700 dark:bg-surface-700 dark:text-surface-400"
          }`}
        >
          Saved
        </button>
        <button
          type="button"
          onClick={() => setMode("custom")}
          className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
            mode === "custom"
              ? "bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
              : "bg-surface-100 text-surface-500 hover:text-surface-700 dark:bg-surface-700 dark:text-surface-400"
          }`}
        >
          Custom Regex
        </button>
      </div>

      {mode === "builtin" ? (
        <div className="grid grid-cols-2 gap-1.5">
          {filteredBuiltin.map(([key, p]) => (
            <button
              key={key}
              type="button"
              onClick={() => { setSelectedId(key); handleAdd(); }}
              className={`rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                selectedId === key
                  ? "bg-brand-50 text-brand-700 ring-1 ring-brand-300 dark:bg-brand-900/20 dark:text-brand-300"
                  : "bg-surface-50 text-surface-600 hover:bg-surface-100 dark:bg-surface-700/50 dark:text-surface-300"
              }`}
            >
              <div className="font-medium">{p.label}</div>
              <div className="mt-0.5 font-mono text-[10px] text-surface-400 truncate">/{p.pattern}/</div>
            </button>
          ))}
        </div>
      ) : mode === "saved" ? (
        <div className="space-y-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search named patterns..."
            className="w-full rounded-lg border border-surface-200 bg-white px-2.5 py-1.5 text-xs focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
          />
          <div className="max-h-32 space-y-0.5 overflow-y-auto">
            {filteredSaved.length === 0 ? (
              <p className="py-2 text-center text-xs text-surface-400">No patterns found</p>
            ) : (
              filteredSaved.map((p) => (
                <label
                  key={p.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs transition-colors ${
                    selectedId === p.id
                      ? "bg-brand-50 text-brand-700 dark:bg-brand-900/20 dark:text-brand-300"
                      : "hover:bg-surface-50 dark:hover:bg-surface-700"
                  }`}
                >
                  <input
                    type="radio"
                    name="pattern-pick"
                    checked={selectedId === p.id}
                    onChange={() => setSelectedId(p.id)}
                    className="text-brand-500 focus:ring-brand-500"
                  />
                  <div>
                    <span className="font-medium">{p.name}</span>
                    <span className="ml-1.5 font-mono text-surface-400">/{p.pattern}/{p.flags}</span>
                  </div>
                </label>
              ))
            )}
          </div>
        </div>
      ) : (
        <RegexBuilder
          pattern={customPattern}
          flags={customFlags}
          onPatternChange={setCustomPattern}
          onFlagsChange={setCustomFlags}
        />
      )}

      <label className="mt-3 flex items-center gap-1.5 cursor-pointer">
        <input
          type="checkbox"
          checked={negate}
          onChange={(e) => setNegate(e.target.checked)}
          className="rounded border-surface-300 text-accent-500 focus:ring-accent-500"
        />
        <span className="text-xs text-surface-600 dark:text-surface-400">Negate (invert match)</span>
      </label>

      <div className="mt-3 flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button
          type="button"
          size="sm"
          onClick={handleAdd}
          disabled={
            (mode === "saved" && !selectedId) ||
            (mode === "custom" && !customPattern)
          }
        >
          Add
        </Button>
      </div>
    </div>
  );
}

function PatternSection({
  label,
  entries,
  onAdd,
  onRemove,
  onToggleNegate,
}: {
  label: string;
  entries: { id?: string; pattern?: string; negate?: boolean }[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onToggleNegate: (index: number) => void;
}) {
  const { data: namedPatterns } = useRegexPatterns();

  const nameMap = useMemo(() => {
    const map: Record<string, string> = {};
    if (namedPatterns) {
      for (const p of namedPatterns) {
        map[p.id] = p.name;
      }
    }
    return map;
  }, [namedPatterns]);

  function describe(entry: { id?: string; pattern?: string }): { badge: string; display: string } {
    if (entry.id) {
      return { badge: "saved", display: nameMap[entry.id] ?? `id:${entry.id.slice(0, 8)}` };
    }
    if (entry.pattern) {
      for (const [key, bp] of Object.entries(BUILT_IN_PATTERNS)) {
        if (bp.pattern === entry.pattern) {
          return { badge: "builtin", display: bp.label };
        }
      }
      return { badge: "regex", display: entry.pattern };
    }
    return { badge: "", display: "" };
  }

  return (
    <div className="mt-2 space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-surface-500">{label}</span>
        <button
          type="button"
          onClick={onAdd}
          className="flex items-center gap-0.5 text-xs text-brand-600 hover:text-brand-700 dark:text-brand-400"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
      </div>
      {entries.length === 0 ? (
        <p className="text-xs text-surface-400 italic">None</p>
      ) : (
        entries.map((entry, i) => {
          const { badge, display } = describe(entry);
          return (
            <div key={i} className="flex items-center gap-2 rounded-lg bg-surface-50 px-2.5 py-1.5 dark:bg-surface-700/50">
              <span className="flex-1 truncate font-mono text-xs text-surface-700 dark:text-surface-200">
                <span className="flex items-center gap-1">
                  {badge ? (
                    <span className={`rounded px-1 py-0.5 text-[10px] font-medium ${
                      badge === "builtin"
                        ? "bg-violet-100 text-violet-600 dark:bg-violet-900/30 dark:text-violet-300"
                        : badge === "saved"
                          ? "bg-brand-100 text-brand-600 dark:bg-brand-900/30 dark:text-brand-300"
                          : "bg-surface-200 text-surface-600 dark:bg-surface-600 dark:text-surface-300"
                    }`}>
                      {badge}
                    </span>
                  ) : null}
                  <span className="truncate">{display}</span>
                </span>
              </span>
              {entry.negate ? (
                <span className="rounded bg-accent-100 px-1 py-0.5 text-[10px] font-medium text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">
                  NOT
                </span>
              ) : null}
              <button
                type="button"
                onClick={() => onToggleNegate(i)}
                className={`rounded p-0.5 text-xs transition-colors ${
                  entry.negate
                    ? "bg-accent-100 text-accent-600 dark:bg-accent-900/20 dark:text-accent-400"
                    : "text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-600"
                }`}
                title={entry.negate ? "Remove negation" : "Negate"}
              >
                !
              </button>
              <button
                type="button"
                onClick={() => onRemove(i)}
                className="rounded p-0.5 text-surface-400 hover:bg-surface-200 hover:text-accent-500 dark:hover:bg-surface-600"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}

export function ValidationRulesDialog({ projectId, docType, open, onOpenChange }: Props) {
  const [rules, setRules] = useState<Record<string, unknown>>({});
  const [openFields, setOpenFields] = useState<Set<string>>(new Set());
  const [addingPatternTo, setAddingPatternTo] = useState<{
    fieldKey: string;
    group: "and_patterns" | "or_patterns";
  } | null>(null);
  const updateDocType = useUpdateDocumentType(projectId);

  const fields = useMemo(() => {
    if (!docType) return [];
    return schemaToFields(docType.schema_definition);
  }, [docType]);

  useEffect(() => {
    if (docType && open) {
      const initial = structuredClone(docType.validation_rules ?? {}) as Record<string, unknown>;
      // Ensure confidence_min defaults to 95 for every field
      const parsed = schemaToFields(docType.schema_definition);
      for (const field of parsed) {
        let fieldRules = initial[field.key] as Record<string, unknown> | undefined;
        if (!fieldRules) {
          fieldRules = {};
          initial[field.key] = fieldRules;
        }
        if (fieldRules.confidence_min === undefined || fieldRules.confidence_min === null) {
          fieldRules.confidence_min = 95;
        }
      }
      setRules(initial);
      setOpenFields(new Set());
      setAddingPatternTo(null);
    }
  }, [docType, open]);

  function getFieldRules(fieldKey: string): Record<string, unknown> {
    return (rules[fieldKey] as Record<string, unknown>) ?? {};
  }

  function setFieldRule(fieldKey: string, ruleKey: string, value: unknown) {
    setRules((prev) => {
      const next = { ...prev };
      let field = { ...(next[fieldKey] as Record<string, unknown> ?? {}) };
      if (value === undefined || value === null || value === "") {
        delete field[ruleKey];
      } else {
        field[ruleKey] = value;
      }
      if (Object.keys(field).length > 0) {
        next[fieldKey] = field;
      } else {
        delete next[fieldKey];
      }
      return next;
    });
  }

  function removeRule(fieldKey: string, ruleKey: string) {
    if (ruleKey === "confidence_min") return; // confidence_min is mandatory
    setFieldRule(fieldKey, ruleKey, undefined);
  }

  function getPatterns(
    fieldKey: string,
    group: "and_patterns" | "or_patterns",
  ): { id?: string; pattern?: string; negate?: boolean }[] {
    const field = rules[fieldKey] as Record<string, unknown> | undefined;
    return (field?.[group] as { id?: string; pattern?: string; negate?: boolean }[]) ?? [];
  }

  function addPattern(
    fieldKey: string,
    group: "and_patterns" | "or_patterns",
    entry: { id?: string; pattern?: string; negate?: boolean },
  ) {
    setRules((prev) => {
      const next = { ...prev };
      let field = { ...(next[fieldKey] as Record<string, unknown> ?? {}) };
      const arr = [...(field[group] as unknown[] ?? []), entry];
      field[group] = arr;
      next[fieldKey] = field;
      return next;
    });
    setAddingPatternTo(null);
  }

  function removePattern(fieldKey: string, group: "and_patterns" | "or_patterns", index: number) {
    setRules((prev) => {
      const next = { ...prev };
      let field = { ...(next[fieldKey] as Record<string, unknown> ?? {}) };
      const arr = [...(field[group] as unknown[] ?? [])];
      arr.splice(index, 1);
      if (arr.length > 0) {
        field[group] = arr;
      } else {
        delete field[group];
      }
      next[fieldKey] = field;
      return next;
    });
  }

  function toggleNegate(fieldKey: string, group: "and_patterns" | "or_patterns", index: number) {
    setRules((prev) => {
      const next = { ...prev };
      let field = { ...(next[fieldKey] as Record<string, unknown> ?? {}) };
      const arr = [...(field[group] as unknown[] ?? [])] as { id?: string; pattern?: string; negate?: boolean }[];
      arr[index] = { ...arr[index], negate: !arr[index].negate };
      field[group] = arr;
      next[fieldKey] = field;
      return next;
    });
  }

  function toggleField(fieldKey: string) {
    setOpenFields((prev) => {
      const next = new Set(prev);
      if (next.has(fieldKey)) next.delete(fieldKey);
      else next.add(fieldKey);
      return next;
    });
  }

  async function handleSave() {
    if (!docType) return;
    try {
      await updateDocType.mutateAsync({
        typeId: docType.id,
        data: { validation_rules: Object.keys(rules).length > 0 ? rules : {} },
      });
      onOpenChange(false);
    } catch {
      // error handled by mutation
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Validation Rules"
      description={docType ? `Configure per-field validation rules for "${docType.name}"` : ""}
      className="sm:max-w-2xl"
    >
      {fields.length === 0 ? (
        <p className="text-sm text-surface-400">No fields defined in schema.</p>
      ) : (
        <div className="max-h-[65vh] space-y-3 overflow-y-auto pr-1">
          {fields.map((field) => {
            const fieldRules = getFieldRules(field.key);
            const activeRules = Object.keys(fieldRules).filter(
              (k) => k !== "and_patterns" && k !== "or_patterns" && k !== "columns",
            );
            const andPatterns = getPatterns(field.key, "and_patterns");
            const orPatterns = getPatterns(field.key, "or_patterns");
            const isOpen = openFields.has(field.key);
            const applicable = getApplicableRules(field.type);
            const availableToAdd = applicable.filter((r) => !activeRules.includes(r));

            return (
              <div key={field.key} className="rounded-xl border border-surface-100 bg-surface-50/50 dark:border-surface-700 dark:bg-surface-800/50">
                <button
                  type="button"
                  onClick={() => toggleField(field.key)}
                  className="flex w-full items-center gap-2 px-3 py-2.5 text-left"
                >
                  <ShieldCheck className="h-4 w-4 shrink-0 text-brand-500" />
                  <span className="text-sm font-semibold text-surface-900 dark:text-surface-100">{field.key}</span>
                  <span className="rounded bg-surface-100 px-1.5 py-0.5 text-[10px] font-medium text-surface-500 dark:bg-surface-700 dark:text-surface-400">{field.type}</span>
                  {(activeRules.length + andPatterns.length + orPatterns.length) > 1 ? (
                    <span className="ml-auto text-xs text-surface-400">
                      {activeRules.length + andPatterns.length + orPatterns.length - 1} rule{(activeRules.length + andPatterns.length + orPatterns.length - 1) !== 1 ? "s" : ""}
                    </span>
                  ) : null}
                  <svg
                    className={`h-4 w-4 text-surface-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {isOpen ? (
                  <div className="border-t border-surface-100 px-3 pb-3 pt-2 dark:border-surface-700">
                    {/* Simple rules — confidence_min is always shown and non-removable */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <label className="w-28 shrink-0 text-xs font-medium text-surface-700 dark:text-surface-300">
                          Confidence min
                        </label>
                        <input
                          type="number"
                          value={(fieldRules.confidence_min as number | undefined) ?? 95}
                          onChange={(e) => setFieldRule(field.key, "confidence_min", e.target.value === "" ? undefined : Number(e.target.value))}
                          placeholder="0–100"
                          className="w-full rounded-lg border border-surface-200 bg-white px-2.5 py-1.5 text-xs focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                        />
                        <div className="w-8" />
                      </div>

                      {activeRules.filter((k) => k !== "confidence_min").map((ruleKey) => (
                        <div key={ruleKey} className="flex items-center gap-2">
                          <label className="w-28 shrink-0 text-xs text-surface-500">{RULE_LABELS[ruleKey] ?? ruleKey}</label>
                          <input
                            type="number"
                            value={(fieldRules[ruleKey] as number | undefined) ?? ""}
                            onChange={(e) => setFieldRule(field.key, ruleKey, e.target.value === "" ? undefined : Number(e.target.value))}
                            placeholder={RULE_DESCRIPTIONS[ruleKey]}
                            className="w-full rounded-lg border border-surface-200 bg-white px-2.5 py-1.5 text-xs focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
                          />
                          <button
                            type="button"
                            onClick={() => removeRule(field.key, ruleKey)}
                            className="rounded p-1 text-surface-400 hover:bg-surface-200 hover:text-accent-500 dark:hover:bg-surface-600"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>

                    {availableToAdd.length > 0 ? (
                      <div className="mt-2">
                        <select
                          value=""
                          onChange={(e) => {
                            const val = e.target.value;
                            if (!val) return;
                            if (val === "and_pattern" || val === "or_pattern") {
                              setAddingPatternTo({ fieldKey: field.key, group: val === "and_pattern" ? "and_patterns" : "or_patterns" });
                              return;
                            }
                            setFieldRule(field.key, val, undefined);
                          }}
                          className="w-full rounded-lg border border-dashed border-surface-300 bg-transparent px-2.5 py-1.5 text-xs text-surface-400 focus:border-brand-500 focus:outline-none dark:border-surface-600 dark:bg-surface-800 dark:text-surface-400"
                        >
                          <option value="">+ Add rule...</option>
                          {availableToAdd.map((r) => (
                            <option key={r} value={r}>{RULE_LABELS[r]}</option>
                          ))}
                          <option value="and_pattern">Pattern (AND — all must pass)</option>
                          <option value="or_pattern">Pattern (OR — at least one must pass)</option>
                        </select>
                      </div>
                    ) : null}

                    {/* Pattern groups */}
                    {addingPatternTo?.fieldKey === field.key ? (
                      <div className="mt-3">
                        <PatternEntryForm
                          onAdd={(entry) => addPattern(field.key, addingPatternTo.group, entry)}
                          onCancel={() => setAddingPatternTo(null)}
                        />
                      </div>
                    ) : null}

                    <PatternSection
                      label={`AND patterns (all must pass) — ${andPatterns.length}`}
                      entries={andPatterns}
                      onAdd={() => setAddingPatternTo({ fieldKey: field.key, group: "and_patterns" })}
                      onRemove={(i) => removePattern(field.key, "and_patterns", i)}
                      onToggleNegate={(i) => toggleNegate(field.key, "and_patterns", i)}
                    />

                    <PatternSection
                      label={`OR patterns (at least one must pass) — ${orPatterns.length}`}
                      entries={orPatterns}
                      onAdd={() => setAddingPatternTo({ fieldKey: field.key, group: "or_patterns" })}
                      onRemove={(i) => removePattern(field.key, "or_patterns", i)}
                      onToggleNegate={(i) => toggleNegate(field.key, "or_patterns", i)}
                    />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-6 flex justify-end gap-3 border-t border-surface-100 pt-4 dark:border-surface-700">
        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="button" onClick={handleSave} isLoading={updateDocType.isPending}>
          Save Rules
        </Button>
      </div>
    </Dialog>
  );
}

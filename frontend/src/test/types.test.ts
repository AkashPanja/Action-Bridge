import { describe, it, expect } from "vitest";
import { fieldsToSchema, schemaToFields, fieldsToValidationRules } from "../components/schema/types";
import type { FieldDefinition } from "../components/schema/types";

describe("fieldsToSchema", () => {
  it("converts a simple string field", () => {
    const fields: FieldDefinition[] = [
      { key: "name", type: "string", title: "Full Name", required: true, enumValues: [] },
    ];
    const schema = fieldsToSchema(fields) as Record<string, unknown>;
    expect(schema).toEqual({
      type: "object",
      title: "Document",
      properties: {
        name: { type: "string", title: "Full Name" },
      },
      required: ["name"],
    });
  });

  it("converts number, boolean, and date fields", () => {
    const fields: FieldDefinition[] = [
      { key: "age", type: "number", title: "Age", required: false, enumValues: [] },
      { key: "active", type: "boolean", title: "Active", required: true, enumValues: [] },
      { key: "dob", type: "date", title: "Date of Birth", required: false, enumValues: [] },
    ];
    const schema = fieldsToSchema(fields) as Record<string, unknown>;
    const props = schema.properties as Record<string, unknown>;
    expect(props.age).toEqual({ type: ["number", "null"], title: "Age" });
    expect(props.active).toEqual({ type: "boolean", title: "Active" });
    expect(props.dob).toEqual({ type: ["string", "null"], title: "Date of Birth", format: "date" });
    expect(schema.required).toEqual(["active"]);
  });

  it("converts enum fields with enum values", () => {
    const fields: FieldDefinition[] = [
      { key: "color", type: "enum", title: "Color", required: true, enumValues: ["red", "green", "blue"] },
    ];
    const schema = fieldsToSchema(fields) as Record<string, unknown>;
    const props = schema.properties as Record<string, unknown>;
    expect(props.color).toEqual({
      type: "string",
      title: "Color",
      enum: ["red", "green", "blue"],
    });
  });

  it("converts table fields with nested columns", () => {
    const fields: FieldDefinition[] = [
      {
        key: "items",
        type: "table",
        title: "Items",
        required: true,
        enumValues: [],
        columns: [
          { key: "sku", type: "string", title: "SKU", required: true, enumValues: [] },
          { key: "qty", type: "number", title: "Quantity", required: false, enumValues: [] },
        ],
      },
    ];
    const schema = fieldsToSchema(fields) as Record<string, unknown>;
    const props = schema.properties as Record<string, unknown>;
    expect(props.items).toEqual({
      type: "array",
      title: "Items",
      items: {
        type: "object",
        properties: {
          sku: { type: "string", title: "SKU" },
          qty: { type: ["number", "null"], title: "Quantity" },
        },
        required: ["sku"],
      },
    });
    expect(schema.required).toEqual(["items"]);
  });

  it("skips fields with empty key", () => {
    const fields: FieldDefinition[] = [
      { key: "", type: "string", title: "", required: false, enumValues: [] },
      { key: "valid", type: "string", title: "Valid", required: true, enumValues: [] },
    ];
    const schema = fieldsToSchema(fields) as Record<string, unknown>;
    const props = schema.properties as Record<string, unknown>;
    expect(props).toEqual({ valid: { type: "string", title: "Valid" } });
    expect(schema.required).toEqual(["valid"]);
  });
});

describe("schemaToFields", () => {
  it("converts a simple JSON Schema to fields", () => {
    const schema = {
      type: "object",
      title: "Document",
      properties: {
        name: { type: "string", title: "Full Name" },
      },
      required: ["name"],
    };
    const fields = schemaToFields(schema);
    expect(fields).toHaveLength(1);
    expect(fields[0]).toEqual({
      key: "name",
      type: "string",
      title: "Full Name",
      required: true,
      enumValues: [],
    });
  });

  it("converts array/table schemas with nested columns", () => {
    const schema = {
      type: "object",
      properties: {
        items: {
          type: "array",
          title: "Items",
          items: {
            type: "object",
            properties: {
              sku: { type: "string", title: "SKU" },
              qty: { type: "number", title: "Qty" },
            },
            required: ["sku"],
          },
        },
      },
      required: ["items"],
    };
    const fields = schemaToFields(schema);
    expect(fields).toHaveLength(1);
    expect(fields[0].key).toBe("items");
    expect(fields[0].type).toBe("table");
    expect(fields[0].required).toBe(true);
    expect(fields[0].columns).toHaveLength(2);
    expect(fields[0].columns![0]).toEqual({
      key: "sku",
      type: "string",
      title: "SKU",
      required: true,
      enumValues: [],
    });
    expect(fields[0].columns![1]).toEqual({
      key: "qty",
      type: "number",
      title: "Qty",
      required: false,
      enumValues: [],
    });
  });

  it("handles date format conversion", () => {
    const schema = {
      type: "object",
      properties: {
        dob: { type: "string", format: "date", title: "DOB" },
      },
    };
    const fields = schemaToFields(schema);
    expect(fields[0].type).toBe("date");
  });
});

describe("fieldsToSchema <-> schemaToFields roundtrip", () => {
  it("produces the same schema after roundtrip for simple fields", () => {
    const fields: FieldDefinition[] = [
      { key: "name", type: "string", title: "Name", required: true, enumValues: [] },
      { key: "age", type: "number", title: "Age", required: false, enumValues: [] },
      { key: "color", type: "enum", title: "Color", required: true, enumValues: ["r", "g", "b"] },
    ];
    const schema = fieldsToSchema(fields);
    const result = schemaToFields(schema);
    expect(result).toEqual(fields);
  });

  it("produces the same schema after roundtrip for table fields", () => {
    const fields: FieldDefinition[] = [
      {
        key: "items",
        type: "table",
        title: "Items",
        required: true,
        enumValues: [],
        columns: [
          { key: "sku", type: "string", title: "SKU", required: true, enumValues: [] },
          { key: "qty", type: "number", title: "Qty", required: false, enumValues: [] },
        ],
      },
    ];
    const schema = fieldsToSchema(fields);
    const result = schemaToFields(schema);
    expect(result).toEqual(fields);
  });
});

describe("fieldsToValidationRules", () => {
  it("returns empty object when no validations", () => {
    const fields: FieldDefinition[] = [
      { key: "name", type: "string", title: "", required: false, enumValues: [] },
    ];
    expect(fieldsToValidationRules(fields)).toEqual({});
  });

  it("extracts validation rules from fields", () => {
    const fields: FieldDefinition[] = [
      {
        key: "name",
        type: "string",
        title: "",
        required: false,
        enumValues: [],
        validations: { min_length: 2, max_length: 100 },
      },
      {
        key: "age",
        type: "number",
        title: "",
        required: false,
        enumValues: [],
        validations: { min_value: 0, max_value: 150 },
      },
    ];
    const rules = fieldsToValidationRules(fields);
    expect(rules).toEqual({
      name: { min_length: 2, max_length: 100 },
      age: { min_value: 0, max_value: 150 },
    });
  });

  it("includes columns validation when parent table field also has validations", () => {
    const fields: FieldDefinition[] = [
      {
        key: "items",
        type: "table",
        title: "",
        required: false,
        enumValues: [],
        validations: { confidence_min: 0.95 },
        columns: [
          { key: "sku", type: "string", title: "", required: false, enumValues: [], validations: { min_length: 1 } },
        ],
      },
    ];
    const rules = fieldsToValidationRules(fields) as Record<string, unknown>;
    const items = rules.items as Record<string, unknown>;
    expect(items).toBeDefined();
    expect(items.confidence_min).toBe(0.95);
    expect(items.columns).toEqual({ sku: { min_length: 1 } });
  });
});

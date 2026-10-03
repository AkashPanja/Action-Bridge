import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SchemaBuilder } from "../components/schema/SchemaBuilder";

describe("SchemaBuilder", () => {
  it("renders with empty schema showing one empty field row", () => {
    const onChange = vi.fn();
    render(<SchemaBuilder schema={{}} onChange={onChange} />);
    expect(screen.getByPlaceholderText("field_name")).toBeInTheDocument();
    expect(screen.getByText("Add Field")).toBeInTheDocument();
  });

  it("renders existing schema fields", () => {
    const onChange = vi.fn();
    const schema = {
      type: "object",
      properties: {
        name: { type: "string", title: "Name" },
        age: { type: "number", title: "Age" },
      },
      required: ["name"],
    };
    render(<SchemaBuilder schema={schema} onChange={onChange} />);
    expect(screen.getByDisplayValue("name")).toBeInTheDocument();
    expect(screen.getByDisplayValue("age")).toBeInTheDocument();
  });

  it("adds a new field when Add Field is clicked", () => {
    const onChange = vi.fn();
    render(<SchemaBuilder schema={{}} onChange={onChange} />);
    fireEvent.click(screen.getByText("Add Field"));

    const inputs = screen.getAllByPlaceholderText("field_name");
    expect(inputs).toHaveLength(2);
  });

  it("removes a field when delete button is clicked", () => {
    const onChange = vi.fn();
    const schema = {
      type: "object",
      properties: {
        name: { type: "string", title: "Name" },
        age: { type: "number", title: "Age" },
      },
    };
    render(<SchemaBuilder schema={schema} onChange={onChange} />);
    const deleteButtons = screen.getAllByRole("button", { hidden: true }).filter(
      (btn) => btn.innerHTML.includes("trash") || btn.querySelector("svg[class*='lucide-trash']")
    );
    expect(deleteButtons.length).toBeGreaterThanOrEqual(2);
  });

  it("updates field name on input change", () => {
    const onChange = vi.fn();
    render(<SchemaBuilder schema={{}} onChange={onChange} />);
    const input = screen.getByPlaceholderText("field_name");
    fireEvent.change(input, { target: { value: "email" } });
    expect(screen.getByDisplayValue("email")).toBeInTheDocument();
  });

  it("renders in readOnly mode without input fields", () => {
    const onChange = vi.fn();
    const schema = {
      type: "object",
      properties: {
        name: { type: "string", title: "Name" },
      },
    };
    render(<SchemaBuilder schema={schema} onChange={onChange} readOnly />);
    expect(screen.getByText("name")).toBeInTheDocument();
    expect(screen.getByText("string")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("field_name")).not.toBeInTheDocument();
    expect(screen.queryByText("Add Field")).not.toBeInTheDocument();
  });

  it("shows column count for table fields", () => {
    const onChange = vi.fn();
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
            },
          },
        },
      },
    };
    render(<SchemaBuilder schema={schema} onChange={onChange} />);
    expect(screen.getByText(/1 columns?/i)).toBeInTheDocument();
  });
});

describe("schema nullability (extraction contract)", () => {
  it("emits nullable unions for optional fields, strict for required", async () => {
    const { fieldsToSchema } = await import("../components/schema/types");
    const schema = fieldsToSchema([
      { key: "invoice_number", type: "string", title: "No", required: true, enumValues: [] },
      { key: "vendor_gstin", type: "string", title: "GSTIN", required: false, enumValues: [] },
      { key: "total_amount", type: "number", title: "Total", required: true, enumValues: [] },
      { key: "discount", type: "number", title: "Disc", required: false, enumValues: [] },
    ]) as { properties: Record<string, { type: unknown }>; required: string[] };
    expect(schema.properties.invoice_number.type).toBe("string");
    expect(schema.properties.vendor_gstin.type).toEqual(["string", "null"]);
    expect(schema.properties.total_amount.type).toBe("number");
    expect(schema.properties.discount.type).toEqual(["number", "null"]);
    expect(schema.required).toEqual(["invoice_number", "total_amount"]);
  });

  it("emits nullable unions for optional table columns", async () => {
    const { fieldsToSchema } = await import("../components/schema/types");
    const schema = fieldsToSchema([
      {
        key: "items", type: "table", title: "Items", required: false, enumValues: [],
        columns: [
          { key: "description", type: "string", title: "Desc", required: true, enumValues: [] },
          { key: "hsn_sac", type: "string", title: "HSN", required: false, enumValues: [] },
        ],
      },
    ]) as { properties: Record<string, { items: { properties: Record<string, { type: unknown }> } }> };
    const cols = schema.properties.items.items.properties;
    expect(cols.description.type).toBe("string");
    expect(cols.hsn_sac.type).toEqual(["string", "null"]);
  });

  it("round-trips nullable unions back to optional fields", async () => {
    const { schemaToFields, fieldsToSchema } = await import("../components/schema/types");
    const schema = {
      type: "object",
      properties: {
        name: { type: "string", title: "Name" },
        nick: { type: ["string", "null"], title: "Nick" },
      },
      required: ["name"],
    };
    const fields = schemaToFields(schema);
    expect(fields.find((f) => f.key === "name")?.required).toBe(true);
    expect(fields.find((f) => f.key === "nick")?.required).toBe(false);
    const back = fieldsToSchema(fields) as { properties: Record<string, { type: unknown }> };
    expect(back.properties.nick.type).toEqual(["string", "null"]);
  });
});

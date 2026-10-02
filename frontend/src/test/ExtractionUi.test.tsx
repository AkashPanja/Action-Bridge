import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { JobsPage } from "../pages/extraction/JobsPage";
import { UploadModal } from "../components/extraction/UploadModal";

const JOBS = [
  {
    id: "job-1", project_id: "p1", kind: "extract", status: "failed",
    attempts: 2, error: "boom", provider_id: null, payload: {}, result: null, usage: null,
  },
  {
    id: "job-2", project_id: "p1", kind: "extract", status: "succeeded",
    attempts: 0, error: null, provider_id: null,
    payload: {}, result: { document_ids: ["d1"] }, usage: null,
  },
];

const retry = vi.fn();
const cancel = vi.fn();

vi.mock("../hooks/useExtraction", () => ({
  useProjectJobs: () => ({ data: { total: 2, jobs: JOBS }, isLoading: false }),
  useJobMutations: () => ({ retry: { mutate: retry }, cancel: { mutate: cancel } }),
  useProfiles: () => ({ data: [] }),
}));

vi.mock("../hooks/useDocumentTypes", () => ({
  useDocumentTypes: () => ({ data: [] }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("JobsPage", () => {
  it("renders jobs with status and error", () => {
    render(<JobsPage projectId="p1" />);
    expect(screen.getByText("failed (try 2)")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
    // badge + filter <option> both read "succeeded"
    expect(screen.getAllByText("succeeded").length).toBeGreaterThanOrEqual(1);
  });

  it("offers retry on failed jobs", () => {
    render(<JobsPage projectId="p1" />);
    fireEvent.click(screen.getByText("Retry"));
    expect(retry).toHaveBeenCalledWith("job-1");
  });

  it("filters by status", () => {
    render(<JobsPage projectId="p1" />);
    const select = screen.getByDisplayValue("All statuses") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "failed" } });
    expect(select.value).toBe("failed");
  });
});

describe("UploadModal", () => {
  it("requires a file before submitting", () => {
    render(<UploadModal projectId="p1" open={true} onClose={() => {}} />);
    fireEvent.click(screen.getByText("Upload & Extract"));
    expect(screen.getByText("Choose at least one file")).toBeInTheDocument();
  });
});

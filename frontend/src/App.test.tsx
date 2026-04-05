import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

const { readWorkbookPreviewMock } = vi.hoisted(() => ({
  readWorkbookPreviewMock: vi.fn(),
}));

vi.mock("ag-grid-react", () => ({
  AgGridReact: ({
    rowData,
    columnDefs,
  }: {
    rowData: unknown[];
    columnDefs: unknown[];
  }) => (
    <div data-testid="mock-grid">
      <span>{JSON.stringify(columnDefs)}</span>
      <span>{JSON.stringify(rowData)}</span>
    </div>
  ),
}));

vi.mock("./lib/workbook", () => ({
  FIXED_HEADERS: {
    customer: "Contact Name",
    insurance: "Insurance",
    rto: "(RTO+ Agent fee 500)",
  },
  readWorkbookPreview: readWorkbookPreviewMock,
}));

import App from "./App";

function buildWorkbookFile() {
  return new File(["mock workbook"], "sales.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

describe("App", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", vi.fn());
    readWorkbookPreviewMock.mockResolvedValue({
      fileName: "sales.xlsx",
      sheetTitle: "Vehicle Sales Register",
      headerRow: [
        "Invoice No.",
        "Contact Name",
        "Insurance",
        "(RTO+ Agent fee 500)",
      ],
      rows: [
        ["INV-1", "Ramesh Kumar", "", ""],
        ["INV-2", "Suresh Sharma", "", ""],
      ],
    });
  });

  it("renders workbook preview after upload", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.upload(
      screen.getByLabelText(/upload excel workbook/i),
      buildWorkbookFile(),
    );

    await waitFor(() =>
      expect(screen.getByText("Vehicle Sales Register")).toBeInTheDocument(),
    );
    expect(screen.getByText("2 data rows")).toBeInTheDocument();
    expect(screen.getByTestId("mock-grid")).toHaveTextContent("Ramesh Kumar");
  });

  it("keeps RTO and insurance uploads isolated by tab", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("tab", { name: /rto receipts/i }));
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto-one.pdf", { type: "application/pdf" }),
    );

    await user.click(screen.getByRole("tab", { name: /insurance files/i }));
    await user.upload(
      screen.getByLabelText(/upload insurance files/i),
      [
        new File(["insurance-a"], "insurance-a.pdf", {
          type: "application/pdf",
        }),
        new File(["insurance-b"], "insurance-b.pdf", {
          type: "application/pdf",
        }),
      ],
    );

    expect(screen.getByText("2 files selected")).toBeInTheDocument();
    expect(screen.getByText("insurance-a.pdf")).toBeInTheDocument();
    expect(screen.getByText("insurance-b.pdf")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /rto receipts/i }));
    expect(screen.getByText("1 files selected")).toBeInTheDocument();
    expect(screen.getByText("rto-one.pdf")).toBeInTheDocument();
  });

  it("processes the workbook and shows result links", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        jobId: "job-1",
        sheetTitle: "Vehicle Sales Register",
        headerRow: [
          "Invoice No.",
          "Contact Name",
          "Insurance",
          "(RTO+ Agent fee 500)",
        ],
        rows: [
          ["INV-1", "Ramesh Kumar", 5400, ""],
          ["INV-2", "Suresh Sharma", "", 3200],
        ],
        summary: {
          billsProcessed: 2,
          billsUpdated: 2,
          rowsUpdated: 2,
          billsReview: 0,
          parseFailures: 0,
          noMatch: 0,
          multiMatch: 0,
          rowConflicts: 0,
        },
        downloadUrl: "/download/job-1/sales_updated.xlsx",
        reviewCsvUrl: "/download/job-1/review_conflicts.csv",
      }),
    } as Response);

    render(<App />);

    await user.upload(
      screen.getByLabelText(/upload excel workbook/i),
      buildWorkbookFile(),
    );
    await user.click(screen.getByRole("tab", { name: /insurance files/i }));
    await user.upload(
      screen.getByLabelText(/upload insurance files/i),
      new File(["insurance"], "insurance.pdf", { type: "application/pdf" }),
    );

    await user.click(
      screen.getByRole("button", { name: /process workbook/i }),
    );

    await waitFor(() =>
      expect(
        screen.getByRole("link", { name: /download updated workbook/i }),
      ).toHaveAttribute("href", "/download/job-1/sales_updated.xlsx"),
    );
    expect(screen.getByText("Rows updated")).toBeInTheDocument();
    expect(screen.getByTestId("mock-grid")).toHaveTextContent("5400");
  });

  it("renders API errors", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({
        error: "Processing failed on the server.",
      }),
    } as Response);

    render(<App />);

    await user.upload(
      screen.getByLabelText(/upload excel workbook/i),
      buildWorkbookFile(),
    );
    await user.click(screen.getByRole("tab", { name: /rto receipts/i }));
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto.pdf", { type: "application/pdf" }),
    );

    await user.click(
      screen.getByRole("button", { name: /process workbook/i }),
    );

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Processing failed on the server.",
      ),
    );
  });
});

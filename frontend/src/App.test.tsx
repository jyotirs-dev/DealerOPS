import { render, screen, waitFor, within } from "@testing-library/react";
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

function buildWorkbookFile(name = "sales.xlsx") {
  return new File(["mock workbook"], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

function processResponse(overrides: Record<string, unknown> = {}) {
  return {
    jobId: "job-1",
    sheetTitle: "Vehicle Sales Register",
    headerRow: [
      "Invoice No.",
      "Contact Name",
      "Insurance",
      "(RTO+ Agent fee 500)",
    ],
    rows: [
      ["INV-1", "Ramesh Kumar", "", 3200],
      ["INV-2", "Suresh Sharma", "", ""],
    ],
    summary: {
      billsProcessed: 2,
      billsUpdated: 1,
      rowsUpdated: 1,
      billsReview: 0,
      parseFailures: 0,
      noMatch: 0,
      multiMatch: 0,
      rowConflicts: 0,
    },
    reviewRows: [],
    downloadUrl: "/download/job-1/rto_updated.xlsx",
    reviewCsvUrl: "/download/job-1/review_conflicts.csv",
    ...overrides,
  };
}

/** Uploads a workbook on the RTO stage, which is the resume-mid-workflow path. */
async function startAtRtoStage(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /stage 2/i }));
  await user.upload(
    screen.getByLabelText(/upload a workbook/i),
    buildWorkbookFile(),
  );
  await waitFor(() =>
    expect(screen.getByLabelText(/upload rto receipts/i)).toBeInTheDocument(),
  );
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

  it("opens on stage 1 with every stage visible in the rail", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /convert raw export/i }),
    ).toBeInTheDocument();

    const rail = screen.getByRole("navigation", { name: /workflow stages/i });
    expect(within(rail).getByText(/stage 1 · convert/i)).toBeInTheDocument();
    expect(within(rail).getByText(/stage 2 · update rto/i)).toBeInTheDocument();
    expect(
      within(rail).getByText(/stage 3 · update insurance/i),
    ).toBeInTheDocument();
    expect(within(rail).getByText(/review & export/i)).toBeInTheDocument();
    expect(within(rail).getByText(/not started/i)).toBeInTheDocument();
  });

  it("flags update stages that have no working file yet", async () => {
    const user = userEvent.setup();
    render(<App />);

    const rail = screen.getByRole("navigation", { name: /workflow stages/i });
    expect(within(rail).getAllByText(/needs a working file/i)).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: /stage 2/i }));
    expect(
      screen.getByText(/generate stage 1 first, or upload a workbook/i),
    ).toBeInTheDocument();
  });

  it("shows the generated result inline without leaving stage 1", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          jobId: "job-9",
          rowsWritten: 42,
          monthYear: "Aug 2026",
          manualColumns: ["Payment Mode"],
          downloadUrl: "/download/job-9/SalesRegister_Aug2026.xlsx",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(["generated workbook"]),
      } as Response);

    render(<App />);

    await user.upload(
      screen.getByLabelText(/upload raw invoice export/i),
      buildWorkbookFile("raw-export.xlsx"),
    );
    await user.click(
      screen.getByRole("button", { name: /generate styled workbook/i }),
    );

    await waitFor(() =>
      expect(screen.getByText(/last run result/i)).toBeInTheDocument(),
    );

    // The result renders in place — stage 1 is still the active stage.
    expect(
      screen.getByRole("heading", { name: /convert raw export/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Aug 2026")).toBeInTheDocument();
    expect(screen.getByText("Payment Mode")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /continue to stage 2/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("SalesRegister_Aug2026.xlsx"),
    ).toBeInTheDocument();
  });

  it("carries the working file into a stage started from an uploaded workbook", async () => {
    const user = userEvent.setup();
    render(<App />);

    await startAtRtoStage(user);

    const rail = screen.getByRole("complementary", {
      name: /workflow overview/i,
    });
    expect(within(rail).getByText("sales.xlsx")).toBeInTheDocument();
    expect(within(rail).getByText(/uploaded manually/i)).toBeInTheDocument();
    expect(
      screen.getByText(/upload at least one rto receipt/i),
    ).toBeInTheDocument();
  });

  it("keeps RTO and insurance uploads separate", async () => {
    const user = userEvent.setup();
    render(<App />);

    await startAtRtoStage(user);
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto-one.pdf", { type: "application/pdf" }),
    );
    expect(screen.getByText("rto-one.pdf")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /stage 3/i }));
    await user.upload(
      screen.getByLabelText(/upload insurance bills/i),
      new File(["ins"], "insurance-a.pdf", { type: "application/pdf" }),
    );
    expect(screen.getByText("insurance-a.pdf")).toBeInTheDocument();
    expect(screen.queryByText("rto-one.pdf")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /stage 2/i }));
    expect(screen.getByText("rto-one.pdf")).toBeInTheDocument();
    expect(screen.queryByText("insurance-a.pdf")).not.toBeInTheDocument();
  });

  it("processes a stage and shows the summary and downloads inline", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => processResponse(),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(["updated workbook"]),
      } as Response);

    render(<App />);

    await startAtRtoStage(user);
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /update rto amounts/i }));

    await waitFor(() =>
      expect(screen.getByText(/last run result/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("Bills processed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /workbook/i })).toHaveAttribute(
      "href",
      "/download/job-1/rto_updated.xlsx",
    );
    expect(screen.getByRole("link", { name: /review csv/i })).toHaveAttribute(
      "href",
      "/download/job-1/review_conflicts.csv",
    );
    expect(
      screen.getByRole("button", { name: /continue to stage 3/i }),
    ).toBeInTheDocument();
  });

  it("surfaces review rows with a readable reason", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () =>
          processResponse({
            summary: {
              billsProcessed: 1,
              billsUpdated: 0,
              rowsUpdated: 0,
              billsReview: 1,
              parseFailures: 0,
              noMatch: 1,
              multiMatch: 0,
              rowConflicts: 0,
            },
            reviewRows: [
              {
                billType: "rto",
                billFile: "rto-review.pdf",
                extractedCustomer: "Unknown Person",
                extractedAmount: "5400",
                bestScore: "72.10",
                candidateSalesRows: "row=2 score=72.10",
                reason: "NO_MATCH",
              },
            ],
          }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(["updated workbook"]),
      } as Response);

    render(<App />);

    await startAtRtoStage(user);
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto-review.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /update rto amounts/i }));

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /review rows/i })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    expect(screen.getByText("Excluded")).toBeInTheDocument();
    expect(
      screen.getByText("No matching sales row cleared the configured threshold."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /worksheet/i }));
    expect(screen.getByTestId("mock-grid")).toHaveTextContent("Ramesh Kumar");
  });

  it("edits extraction settings once for every stage", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(
      screen.getByRole("button", { name: /extraction settings/i }),
    );

    const drawer = screen.getByRole("dialog", { name: /extraction settings/i });
    const customerLabels = within(drawer).getByLabelText(/customer labels/i);
    await user.clear(customerLabels);
    await user.type(customerLabels, "Policy Holder");
    await user.click(within(drawer).getByRole("button", { name: /next line/i }));
    await user.click(within(drawer).getByRole("button", { name: /done/i }));

    expect(
      screen.queryByRole("dialog", { name: /extraction settings/i }),
    ).not.toBeInTheDocument();

    // The same settings are still there from a different stage.
    await user.click(screen.getByRole("button", { name: /stage 3/i }));
    await user.click(
      screen.getByRole("button", { name: /extraction settings/i }),
    );
    const reopened = screen.getByRole("dialog", {
      name: /extraction settings/i,
    });
    expect(within(reopened).getByLabelText(/customer labels/i)).toHaveValue(
      "Policy Holder",
    );
    expect(
      within(reopened).getByRole("button", { name: /next line/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("sends the shared settings with a processing request", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => processResponse(),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(["updated workbook"]),
      } as Response);

    render(<App />);

    await user.click(
      screen.getByRole("button", { name: /extraction settings/i }),
    );
    const drawer = screen.getByRole("dialog", { name: /extraction settings/i });
    await user.click(within(drawer).getByRole("button", { name: /next line/i }));
    await user.click(within(drawer).getByRole("button", { name: /done/i }));

    await startAtRtoStage(user);
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /update rto amounts/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(body.get("amount_position")).toBe("next_line");
    expect(body.get("clear_existing")).toBe("0");
  });

  it("lists every completed output in the review stage", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => processResponse(),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(["updated workbook"]),
      } as Response);

    render(<App />);

    await user.click(screen.getByRole("button", { name: /review & export/i }));
    expect(screen.getByText(/no completed stages yet/i)).toBeInTheDocument();

    await startAtRtoStage(user);
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /update rto amounts/i }));
    await waitFor(() =>
      expect(screen.getByText(/last run result/i)).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /review & export/i }));
    expect(
      screen.getByRole("link", { name: /download final workbook/i }),
    ).toHaveAttribute("href", "/download/job-1/rto_updated.xlsx");
    expect(
      screen.getByRole("button", { name: /stage 2 rto updated workbook/i }),
    ).toBeInTheDocument();
  });

  it("renders API errors", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({ error: "Processing failed on the server." }),
    } as Response);

    render(<App />);

    await startAtRtoStage(user);
    await user.upload(
      screen.getByLabelText(/upload rto receipts/i),
      new File(["rto"], "rto.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /update rto amounts/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Processing failed on the server.",
      ),
    );
  });

  it("reports a workbook that cannot be read", async () => {
    const user = userEvent.setup();
    readWorkbookPreviewMock.mockRejectedValue(
      new Error("Workbook must contain a worksheet with headers."),
    );
    render(<App />);

    await user.click(screen.getByRole("button", { name: /stage 2/i }));
    await user.upload(
      screen.getByLabelText(/upload a workbook/i),
      buildWorkbookFile("broken.xlsx"),
    );

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Workbook must contain a worksheet with headers.",
      ),
    );
  });
});

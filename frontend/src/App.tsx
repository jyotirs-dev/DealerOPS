import { useState } from "react";
import type { ChangeEvent } from "react";

import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";

import { FIXED_HEADERS, readWorkbookPreview, type WorkbookPreview } from "./lib/workbook";

type ActiveTab = "sales" | "rto" | "insurance";

type Settings = {
  customerLabels: string;
  amountLabels: string;
  amountPosition: "same_line" | "next_line";
  nameThreshold: string;
  clearExisting: boolean;
};

type ProcessSummary = {
  billsProcessed: number;
  billsUpdated: number;
  rowsUpdated: number;
  billsReview: number;
  parseFailures: number;
  noMatch: number;
  multiMatch: number;
  rowConflicts: number;
};

type ProcessResponse = {
  jobId: string;
  sheetTitle: string;
  headerRow: string[];
  rows: Array<Array<string | number | boolean | null>>;
  summary: ProcessSummary;
  downloadUrl: string;
  reviewCsvUrl: string;
};

type GridRow = Record<string, string | number | boolean | null>;

const DEFAULT_SETTINGS: Settings = {
  customerLabels: "Insured, Insured Name, Received From",
  amountLabels:
    "Received with Thanks Rs, Grand Total (in Rs), Grand Total, Final Amount, Amount Payable, Net Payable",
  amountPosition: "same_line",
  nameThreshold: "95",
  clearExisting: false,
};

const TAB_COPY: Record<ActiveTab, { title: string; hint: string }> = {
  sales: {
    title: "Sales Sheet",
    hint: "Upload the Excel workbook, validate the fixed headers, and preview the target worksheet before processing.",
  },
  rto: {
    title: "RTO Receipts",
    hint: "Drop in one or more RTO bills. PDFs and image formats are supported.",
  },
  insurance: {
    title: "Insurance Files",
    hint: "Upload insurance PDFs or scans. The parser uses the advanced settings below when matching values.",
  },
};

function buildGridModel(preview: WorkbookPreview | null): {
  columnDefs: ColDef<GridRow>[];
  rowData: GridRow[];
} {
  if (!preview) {
    return {
      columnDefs: [],
      rowData: [],
    };
  }

  const columnDefs: ColDef<GridRow>[] = [
    {
      headerName: "#",
      field: "__rowNumber",
      width: 90,
      pinned: "left",
      sortable: false,
      filter: false,
      suppressMovable: true,
      cellClass: "row-number-cell",
    },
    ...preview.headerRow.map((header, index) => ({
      field: `col_${index}`,
      headerName: header || `Column ${index + 1}`,
      sortable: true,
      filter: true,
      resizable: true,
      flex: 1,
      minWidth: 180,
      tooltipField: `col_${index}`,
    })),
  ];

  const rowData = preview.rows.map((row, rowIndex) => {
    const record: GridRow = {
      __rowNumber: rowIndex + 2,
    };
    preview.headerRow.forEach((_, index) => {
      record[`col_${index}`] = row[index] ?? "";
    });
    return record;
  });

  return { columnDefs, rowData };
}

function fileListToArray(fileList: FileList | null): File[] {
  return fileList ? Array.from(fileList) : [];
}

function renderFileList(files: File[]) {
  if (files.length === 0) {
    return <p className="empty-state">No files uploaded yet.</p>;
  }

  return (
    <ul className="file-list">
      {files.map((file) => (
        <li key={`${file.name}-${file.size}`}>{file.name}</li>
      ))}
    </ul>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("sales");
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [workbookFile, setWorkbookFile] = useState<File | null>(null);
  const [workbookPreview, setWorkbookPreview] = useState<WorkbookPreview | null>(
    null,
  );
  const [workbookError, setWorkbookError] = useState<string | null>(null);
  const [rtoFiles, setRtoFiles] = useState<File[]>([]);
  const [insuranceFiles, setInsuranceFiles] = useState<File[]>([]);
  const [processError, setProcessError] = useState<string | null>(null);
  const [processResult, setProcessResult] = useState<ProcessResponse | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const { columnDefs, rowData } = buildGridModel(workbookPreview);
  const canProcess =
    workbookFile !== null &&
    (rtoFiles.length > 0 || insuranceFiles.length > 0) &&
    !isProcessing;

  const readinessMessage = isProcessing
    ? "Processing workbook..."
    : workbookFile === null
      ? "Upload the sales workbook to continue."
      : rtoFiles.length === 0 && insuranceFiles.length === 0
        ? "Upload at least one RTO receipt or insurance file."
        : workbookError
          ? "Workbook preview is unavailable, but you can still process the uploaded file."
          : "Ready to process the uploaded workbook.";

  async function handleWorkbookUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setWorkbookFile(file);
    setProcessResult(null);
    setProcessError(null);

    if (!file) {
      setWorkbookPreview(null);
      setWorkbookError(null);
      return;
    }

    try {
      const preview = await readWorkbookPreview(file);
      setWorkbookPreview(preview);
      setWorkbookError(null);
    } catch (error) {
      setWorkbookPreview(null);
      setWorkbookError(
        error instanceof Error ? error.message : "Failed to read workbook.",
      );
    }
  }

  function handleSettingsChange(
    key: keyof Settings,
    value: string | boolean,
  ) {
    setSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  async function handleProcess() {
    if (!canProcess || !workbookFile) {
      return;
    }

    const formData = new FormData();
    formData.append("workbook", workbookFile);
    insuranceFiles.forEach((file) => formData.append("insurance_files[]", file));
    rtoFiles.forEach((file) => formData.append("rto_files[]", file));
    formData.append("customer_labels", settings.customerLabels);
    formData.append("amount_labels", settings.amountLabels);
    formData.append("amount_position", settings.amountPosition);
    formData.append("name_threshold", settings.nameThreshold);
    formData.append("clear_existing", settings.clearExisting ? "1" : "0");

    setIsProcessing(true);
    setProcessError(null);

    try {
      const response = await fetch("/api/process", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.error ?? "Processing failed.");
      }

      const result = payload as ProcessResponse;
      setProcessResult(result);
      try {
        const workbookResponse = await fetch(result.downloadUrl);
        if (!workbookResponse.ok) {
          throw new Error("Failed to reload updated workbook preview.");
        }
        const workbookBlob = await workbookResponse.blob();
        const refreshedPreview = await readWorkbookPreview(
          new File([workbookBlob], workbookFile.name, {
            type:
              workbookFile.type ||
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          }),
        );
        setWorkbookPreview(refreshedPreview);
      } catch {
        setWorkbookPreview({
          fileName: workbookFile.name,
          sheetTitle: result.sheetTitle,
          headerRow: result.headerRow,
          rows: result.rows,
        });
      }
      setActiveTab("sales");
    } catch (error) {
      setProcessError(
        error instanceof Error ? error.message : "Processing failed.",
      );
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace-grid">
        <div className="control-panel">
          <div className="compact-header">
            <p className="eyebrow">Excel-first reconciliation</p>
            <h1>Workbook updater</h1>
            <p className="compact-copy">
              Upload the sales workbook, add receipt files, and download the
              updated Excel output.
            </p>
            <div className="status-chip-row">
              <span className="status-chip">{FIXED_HEADERS.customer}</span>
              <span className="status-chip">{FIXED_HEADERS.insurance}</span>
              <span className="status-chip">{FIXED_HEADERS.rto}</span>
            </div>
          </div>

          <div className="tab-strip" role="tablist" aria-label="Upload tabs">
            {(["sales", "rto", "insurance"] as ActiveTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                className={activeTab === tab ? "tab-button active" : "tab-button"}
                onClick={() => setActiveTab(tab)}
              >
                {TAB_COPY[tab].title}
              </button>
            ))}
          </div>

          <div className="tab-card">
            <h2>{TAB_COPY[activeTab].title}</h2>
            <p className="tab-hint">{TAB_COPY[activeTab].hint}</p>

            {activeTab === "sales" && (
              <div className="upload-stack">
                <label className="field-label" htmlFor="workbook-upload">
                  Upload Excel workbook
                </label>
                <input
                  id="workbook-upload"
                  name="workbook-upload"
                  type="file"
                  accept=".xlsx,.xlsm"
                  onChange={handleWorkbookUpload}
                />
                <div className="status-chip-row">
                  <span className="status-chip">
                    Workbook: {workbookFile ? workbookFile.name : "Not loaded"}
                  </span>
                  <span className="status-chip">
                    Sheet: {workbookPreview ? workbookPreview.sheetTitle : "Pending"}
                  </span>
                  <span className="status-chip">
                    Rows: {workbookPreview ? workbookPreview.rows.length : 0}
                  </span>
                </div>
                {workbookError ? (
                  <p className="error-banner" role="alert">
                    {workbookError}
                  </p>
                ) : null}
              </div>
            )}

            {activeTab === "rto" && (
              <div className="upload-stack">
                <label className="field-label" htmlFor="rto-upload">
                  Upload RTO receipts
                </label>
                <input
                  id="rto-upload"
                  name="rto-upload"
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
                  multiple
                  onChange={(event) => setRtoFiles(fileListToArray(event.target.files))}
                />
                <span className="status-chip">{rtoFiles.length} files selected</span>
                {renderFileList(rtoFiles)}
              </div>
            )}

            {activeTab === "insurance" && (
              <div className="upload-stack">
                <label className="field-label" htmlFor="insurance-upload">
                  Upload insurance files
                </label>
                <input
                  id="insurance-upload"
                  name="insurance-upload"
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
                  multiple
                  onChange={(event) =>
                    setInsuranceFiles(fileListToArray(event.target.files))
                  }
                />
                <span className="status-chip">
                  {insuranceFiles.length} files selected
                </span>
                {renderFileList(insuranceFiles)}
              </div>
            )}
          </div>

          <details className="advanced-panel">
            <summary>Advanced parser settings</summary>
            <div className="advanced-grid">
              <label>
                Customer labels
                <input
                  type="text"
                  value={settings.customerLabels}
                  onChange={(event) =>
                    handleSettingsChange("customerLabels", event.target.value)
                  }
                />
              </label>
              <label>
                Amount labels
                <input
                  type="text"
                  value={settings.amountLabels}
                  onChange={(event) =>
                    handleSettingsChange("amountLabels", event.target.value)
                  }
                />
              </label>
              <label>
                Amount position
                <select
                  value={settings.amountPosition}
                  onChange={(event) =>
                    handleSettingsChange(
                      "amountPosition",
                      event.target.value as Settings["amountPosition"],
                    )
                  }
                >
                  <option value="same_line">On same line as label</option>
                  <option value="next_line">On next line after label</option>
                </select>
              </label>
              <label>
                Name threshold
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={settings.nameThreshold}
                  onChange={(event) =>
                    handleSettingsChange("nameThreshold", event.target.value)
                  }
                />
              </label>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={settings.clearExisting}
                  onChange={(event) =>
                    handleSettingsChange("clearExisting", event.target.checked)
                  }
                />
                Clear existing Insurance / RTO values before writing matches
              </label>
            </div>
          </details>

          <div className="action-row">
            <button
              type="button"
              className="primary-button"
              onClick={handleProcess}
              disabled={!canProcess}
            >
              {isProcessing ? "Processing workbook..." : "Process workbook"}
            </button>
            <p className="process-note">
              {readinessMessage}
            </p>
            <p className="process-note">
              Downloaded workbook is the v1 output. Google Sheets export is intentionally deferred.
            </p>
          </div>

          {processError ? (
            <p className="error-banner" role="alert">
              {processError}
            </p>
          ) : null}
        </div>

        <div className="preview-panel">
          <div className="preview-header">
            <div>
              <p className="eyebrow">Worksheet preview</p>
              <h2>{workbookPreview ? workbookPreview.sheetTitle : "Awaiting workbook"}</h2>
            </div>
            {processResult ? (
              <div className="result-links">
                <a href={processResult.downloadUrl}>Download updated workbook</a>
                <a href={processResult.reviewCsvUrl}>Download review CSV</a>
              </div>
            ) : null}
          </div>

          {processResult ? (
            <div className="summary-grid">
              <article>
                <span>Total bills</span>
                <strong>{processResult.summary.billsProcessed}</strong>
              </article>
              <article>
                <span>Values updated</span>
                <strong>{processResult.summary.billsUpdated}</strong>
              </article>
              <article>
                <span>Rows updated</span>
                <strong>{processResult.summary.rowsUpdated}</strong>
              </article>
              <article>
                <span>Review rows</span>
                <strong>{processResult.summary.billsReview}</strong>
              </article>
            </div>
          ) : null}

          <div className="preview-meta">
            <span>{workbookPreview ? `${workbookPreview.headerRow.length} columns` : "0 columns"}</span>
            <span>{workbookPreview ? `${workbookPreview.rows.length} data rows` : "0 data rows"}</span>
            <span>{rtoFiles.length + insuranceFiles.length} receipt files loaded</span>
          </div>

          <div className="grid-shell" aria-label="sheet preview">
            {workbookPreview ? (
              <div className="ag-theme-quartz grid-theme">
                <AgGridReact<GridRow>
                  theme="legacy"
                  rowData={rowData}
                  columnDefs={columnDefs}
                  animateRows
                  pagination
                  paginationPageSize={25}
                />
              </div>
            ) : (
              <div className="empty-grid">
                Upload an Excel workbook to preview the worksheet grid.
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

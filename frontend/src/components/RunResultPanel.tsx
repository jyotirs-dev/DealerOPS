import { useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";

import type {
  PreviewMode,
  ReviewRow,
  WorkflowArtifact,
} from "../workflowTypes";
import { AlertIcon, ArrowRightIcon, DownloadIcon } from "./icons";

type GridRow = Record<string, string | number | boolean | null>;

const REVIEW_REASON_COPY: Record<string, string> = {
  NO_MATCH: "No matching sales row cleared the configured threshold.",
  MULTIPLE_SALES_ROWS: "Multiple sales rows matched the extracted customer.",
  MULTIPLE_BILLS_FOR_ROW_TYPE:
    "Multiple bills claimed the same sales row for this bill type.",
  EXISTING_TARGET_VALUE:
    "An existing Insurance / RTO value was preserved because Clear existing was off.",
};

function buildGridModel(preview: WorkflowArtifact["workbookPreview"]): {
  columnDefs: ColDef<GridRow>[];
  rowData: GridRow[];
} {
  if (!preview) {
    return { columnDefs: [], rowData: [] };
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
    const record: GridRow = { __rowNumber: rowIndex + 2 };
    preview.headerRow.forEach((_, index) => {
      record[`col_${index}`] = row[index] ?? "";
    });
    return record;
  });

  return { columnDefs, rowData };
}

function formatReviewReasonSegment(reason: string): string {
  const trimmedReason = reason.trim();
  if (!trimmedReason) {
    return "";
  }
  if (trimmedReason in REVIEW_REASON_COPY) {
    return REVIEW_REASON_COPY[trimmedReason];
  }
  if (trimmedReason.startsWith("TEXT_EXTRACTION_ERROR:")) {
    return trimmedReason.replace(
      "TEXT_EXTRACTION_ERROR:",
      "Text extraction failed:",
    );
  }
  return trimmedReason;
}

function formatReviewReason(reason: string): string {
  return reason
    .split(";")
    .map((part) => formatReviewReasonSegment(part))
    .filter(Boolean)
    .join("; ");
}

function ReviewTable({ reviewRows }: { reviewRows: ReviewRow[] }) {
  return (
    <div className="review-screen">
      <p className="review-intro">
        These bills were excluded from the automatic update because the match
        could not be confirmed confidently, or an existing value was preserved.
      </p>
      <div className="review-table-shell">
        <table className="review-table">
          <thead>
            <tr>
              <th scope="col">Bill</th>
              <th scope="col">Type</th>
              <th scope="col">Extracted customer</th>
              <th scope="col">Amount</th>
              <th scope="col">Status</th>
              <th scope="col">Reason</th>
              <th scope="col">Candidates</th>
            </tr>
          </thead>
          <tbody>
            {reviewRows.map((row) => (
              <tr key={`${row.billType}-${row.billFile}-${row.reason}`}>
                <td className="review-cell-strong">{row.billFile}</td>
                <td>{row.billType}</td>
                <td>{row.extractedCustomer || "Not found"}</td>
                <td>{row.extractedAmount || "Not found"}</td>
                <td>
                  <span className="review-status-pill">Excluded</span>
                </td>
                <td>{formatReviewReason(row.reason)}</td>
                <td>{row.candidateSalesRows || row.bestScore || "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type RunResultPanelProps = {
  artifact: WorkflowArtifact;
  title: string;
  compact?: boolean;
  continueLabel?: string;
  onContinue?: () => void;
};

export function RunResultPanel({
  artifact,
  title,
  compact = false,
  continueLabel,
  onContinue,
}: RunResultPanelProps) {
  const reviewRows = artifact.reviewRows ?? [];
  const hasReviewRows = reviewRows.length > 0;
  const [previewMode, setPreviewMode] = useState<PreviewMode>(
    hasReviewRows ? "review" : "worksheet",
  );
  const { columnDefs, rowData } = buildGridModel(artifact.workbookPreview);

  return (
    <section className="result-panel">
      <header className="result-panel-header">
        <div className="result-panel-heading">
          <span className={hasReviewRows ? "result-dot warning" : "result-dot"} />
          <h2>{title}</h2>
        </div>
        <div className="result-panel-downloads">
          <a className="ghost-button" href={artifact.workbookDownloadUrl}>
            <DownloadIcon />
            Workbook
          </a>
          {artifact.reviewCsvUrl ? (
            <a className="ghost-button" href={artifact.reviewCsvUrl}>
              <DownloadIcon />
              Review CSV
            </a>
          ) : null}
        </div>
      </header>

      {artifact.summary ? (
        <div className="stat-row">
          <article className="stat-tile">
            <span>Bills processed</span>
            <strong>{artifact.summary.billsProcessed}</strong>
          </article>
          <article className="stat-tile success">
            <span>Values updated</span>
            <strong>{artifact.summary.billsUpdated}</strong>
          </article>
          <article className="stat-tile">
            <span>Rows updated</span>
            <strong>{artifact.summary.rowsUpdated}</strong>
          </article>
          <article
            className={
              artifact.summary.billsReview > 0
                ? "stat-tile warning"
                : "stat-tile"
            }
          >
            <span>Flagged for review</span>
            <strong>{artifact.summary.billsReview}</strong>
          </article>
        </div>
      ) : null}

      {artifact.stage === "convert" ? (
        <div className="stat-row">
          <article className="stat-tile">
            <span>Rows written</span>
            <strong>{artifact.rowsWritten ?? 0}</strong>
          </article>
          <article className="stat-tile">
            <span>Detected month</span>
            <strong>{artifact.monthYear || "Unknown"}</strong>
          </article>
        </div>
      ) : null}

      {artifact.manualColumns?.length ? (
        <div className="manual-cols-container">
          <div className="manual-cols-title">Manual entry columns</div>
          <div className="manual-cols-grid">
            {artifact.manualColumns.map((column) => (
              <span className="manual-col-chip" key={column}>
                {column}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="result-preview-bar">
        <div className="preview-meta">
          <span>
            {artifact.workbookPreview
              ? `${artifact.workbookPreview.headerRow.length} columns`
              : "0 columns"}
          </span>
          <span>
            {artifact.workbookPreview
              ? `${artifact.workbookPreview.rows.length} data rows`
              : "0 data rows"}
          </span>
          <span>Source: {artifact.sourceWorkbookFileName}</span>
        </div>

        {hasReviewRows ? (
          <div
            className="preview-switcher"
            role="tablist"
            aria-label="Preview views"
          >
            <button
              type="button"
              role="tab"
              aria-selected={previewMode === "worksheet"}
              className={
                previewMode === "worksheet"
                  ? "preview-toggle active"
                  : "preview-toggle"
              }
              onClick={() => setPreviewMode("worksheet")}
            >
              Worksheet
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={previewMode === "review"}
              className={
                previewMode === "review"
                  ? "preview-toggle active warning"
                  : "preview-toggle"
              }
              onClick={() => setPreviewMode("review")}
            >
              <AlertIcon size={12} />
              Review rows ({reviewRows.length})
            </button>
          </div>
        ) : null}
      </div>

      <div
        className={compact ? "grid-shell compact" : "grid-shell"}
        aria-label={previewMode === "review" ? "review rows" : "sheet preview"}
      >
        {previewMode === "review" && hasReviewRows ? (
          <ReviewTable reviewRows={reviewRows} />
        ) : artifact.workbookPreview ? (
          <div className="ag-theme-quartz grid-theme">
            <AgGridReact<GridRow>
              theme="legacy"
              rowData={rowData}
              columnDefs={columnDefs}
              animateRows
              pagination
              paginationPageSize={20}
            />
          </div>
        ) : (
          <div className="empty-grid">
            This workbook could not be previewed in the browser. Download it to
            inspect the contents.
          </div>
        )}
      </div>

      {onContinue && continueLabel ? (
        <footer className="result-panel-footer">
          <span className="process-note">
            {hasReviewRows
              ? `${reviewRows.length} bill${reviewRows.length === 1 ? "" : "s"} need a manual look before you continue.`
              : "Everything matched cleanly."}
          </span>
          <button type="button" className="primary-button" onClick={onContinue}>
            {continueLabel}
            <ArrowRightIcon />
          </button>
        </footer>
      ) : null}
    </section>
  );
}

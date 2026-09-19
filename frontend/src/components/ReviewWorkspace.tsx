import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";

import type {
  PreviewMode,
  ReviewRow,
  WorkflowArtifact,
} from "../workflowTypes";

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

function formatReviewReasonSegment(reason: string): string {
  const trimmedReason = reason.trim();
  if (!trimmedReason) {
    return "";
  }

  if (trimmedReason in REVIEW_REASON_COPY) {
    return REVIEW_REASON_COPY[trimmedReason];
  }

  if (trimmedReason.startsWith("TEXT_EXTRACTION_ERROR:")) {
    return trimmedReason.replace("TEXT_EXTRACTION_ERROR:", "Text extraction failed:");
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

function renderReviewTable(reviewRows: ReviewRow[]) {
  return (
    <div className="review-screen">
      <p className="review-intro">
        These rows were excluded from automatic updates because the verification
        step could not confirm them confidently or the current settings
        preserved an existing value.
      </p>
      <div className="review-table-shell">
        <table className="review-table">
          <thead>
            <tr>
              <th scope="col">Bill</th>
              <th scope="col">Type</th>
              <th scope="col">Extracted customer</th>
              <th scope="col">Amount</th>
              <th scope="col">Verification</th>
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

type ReviewWorkspaceProps = {
  artifacts: WorkflowArtifact[];
  selectedArtifactId: string | null;
  previewMode: PreviewMode;
  onSelectArtifact: (artifactId: string) => void;
  onPreviewModeChange: (mode: PreviewMode) => void;
};

export function ReviewWorkspace({
  artifacts,
  selectedArtifactId,
  previewMode,
  onSelectArtifact,
  onPreviewModeChange,
}: ReviewWorkspaceProps) {
  const orderedArtifacts = [...artifacts].sort(
    (left, right) => right.completedOrder - left.completedOrder,
  );
  const selectedArtifact =
    orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId)
    ?? orderedArtifacts[0]
    ?? null;
  const reviewRows = selectedArtifact?.reviewRows ?? [];
  const hasReviewRows = reviewRows.length > 0;
  const { columnDefs, rowData } = buildGridModel(selectedArtifact?.workbookPreview);

  return (
    <section className="workspace-grid">
      <div className="control-panel">
        <div className="tab-card">
          <h2>Review & Download</h2>
          <p className="tab-hint">
            Inspect every completed workbook artifact, switch between stage
            outputs, and download the workbook or review CSV for the selected
            stage.
          </p>
        </div>

        {orderedArtifacts.length > 0 ? (
          <div className="artifact-selector-list" role="tablist" aria-label="Completed artifacts">
            {orderedArtifacts.map((artifact) => (
              <button
                key={artifact.id}
                type="button"
                role="tab"
                aria-selected={selectedArtifact?.id === artifact.id}
                className={selectedArtifact?.id === artifact.id ? "artifact-selector active" : "artifact-selector"}
                onClick={() => onSelectArtifact(artifact.id)}
              >
                <span className="artifact-selector-label">{artifact.displayLabel}</span>
                <span className="artifact-selector-meta">
                  {artifact.workbookFileName}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-grid workflow-empty-state">
            No completed artifacts yet. Finish stage 1 or run a later stage
            with a workbook override to populate this workspace.
          </div>
        )}

        {orderedArtifacts.length > 0 ? (
          <div className="artifact-card-list">
            {orderedArtifacts.map((artifact) => (
              <article key={`${artifact.id}-downloads`} className="artifact-card">
                <div className="artifact-card-topline">
                  <strong>{artifact.displayLabel}</strong>
                </div>
                <div className="result-links artifact-download-links">
                  <a href={artifact.workbookDownloadUrl}>Download workbook</a>
                  {artifact.reviewCsvUrl ? (
                    <a href={artifact.reviewCsvUrl}>Download review CSV</a>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>

      <div className="preview-panel">
        <div className="preview-header">
          <div>
            <p className="eyebrow">
              {previewMode === "review" && hasReviewRows
                ? "Review verification"
                : "Worksheet preview"}
            </p>
            <h2>
              {selectedArtifact
                ? selectedArtifact.displayLabel
                : "Awaiting completed workflow artifact"}
            </h2>
          </div>

          <div className="preview-toolbar">
            {hasReviewRows ? (
              <div className="preview-switcher" role="tablist" aria-label="Preview views">
                <button
                  type="button"
                  role="tab"
                  aria-selected={previewMode === "worksheet"}
                  className={previewMode === "worksheet" ? "preview-toggle active" : "preview-toggle"}
                  onClick={() => onPreviewModeChange("worksheet")}
                >
                  Worksheet
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={previewMode === "review"}
                  className={previewMode === "review" ? "preview-toggle active" : "preview-toggle"}
                  onClick={() => onPreviewModeChange("review")}
                >
                  Review rows
                </button>
              </div>
            ) : null}

            {selectedArtifact ? (
              <div className="result-links">
                <a href={selectedArtifact.workbookDownloadUrl}>Download selected workbook</a>
                {selectedArtifact.reviewCsvUrl ? (
                  <a href={selectedArtifact.reviewCsvUrl}>Download selected review CSV</a>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        {selectedArtifact?.summary ? (
          <div className="summary-grid">
            <article>
              <span>Total bills</span>
              <strong>{selectedArtifact.summary.billsProcessed}</strong>
            </article>
            <article>
              <span>Values updated</span>
              <strong>{selectedArtifact.summary.billsUpdated}</strong>
            </article>
            <article>
              <span>Rows updated</span>
              <strong>{selectedArtifact.summary.rowsUpdated}</strong>
            </article>
            <article>
              <span>Review rows</span>
              <strong>{selectedArtifact.summary.billsReview}</strong>
            </article>
          </div>
        ) : null}

        {selectedArtifact?.stage === "convert" ? (
          <div className="summary-grid">
            <article>
              <span>Rows written</span>
              <strong>{selectedArtifact.rowsWritten ?? 0}</strong>
            </article>
            <article>
              <span>Detected month</span>
              <strong>{selectedArtifact.monthYear || "Unknown"}</strong>
            </article>
          </div>
        ) : null}

        {selectedArtifact?.manualColumns?.length ? (
          <div className="manual-cols-container review-manual-columns">
            <div className="manual-cols-title">Manual entry columns</div>
            <div className="manual-cols-grid">
              {selectedArtifact.manualColumns.map((column) => (
                <span className="manual-col-chip" key={column}>
                  {column}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="preview-meta">
          <span>
            {selectedArtifact?.workbookPreview
              ? `${selectedArtifact.workbookPreview.headerRow.length} columns`
              : "0 columns"}
          </span>
          <span>
            {selectedArtifact?.workbookPreview
              ? `${selectedArtifact.workbookPreview.rows.length} data rows`
              : "0 data rows"}
          </span>
          <span>
            {selectedArtifact
              ? `Source: ${selectedArtifact.sourceWorkbookFileName}`
              : "No source workbook"}
          </span>
          {selectedArtifact?.reviewRows ? (
            <span>{selectedArtifact.reviewRows.length} review rows flagged</span>
          ) : null}
        </div>

        <div
          className="grid-shell"
          aria-label={previewMode === "review" ? "review rows" : "sheet preview"}
        >
          {previewMode === "review" && hasReviewRows ? (
            renderReviewTable(reviewRows)
          ) : selectedArtifact?.workbookPreview ? (
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
              Select a completed artifact to preview its workbook.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

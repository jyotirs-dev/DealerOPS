import { useState } from "react";
import { AgGridReact } from "ag-grid-react";

import type {
  PreviewMode,
  ReviewRow,
  WorkflowArtifact,
} from "../workflowTypes";
import { buildGridModel } from "../lib/gridModel";
import type { GridRow } from "../lib/gridModel";
import { NeedsAttentionList } from "./NeedsAttentionList";
import { AlertIcon, ArrowRightIcon, CheckIcon, DownloadIcon } from "./icons";

type RunResultPanelProps = {
  artifact: WorkflowArtifact;
  title: string;
  compact?: boolean;
  continueLabel?: string;
  onContinue?: () => void;
  onApplyManualEdit?: (
    artifactId: string,
    reviewRow: ReviewRow,
    rowNumber: number,
    value: number,
  ) => Promise<void>;
  onDismissReviewRow?: (artifactId: string, reviewRow: ReviewRow) => void;
  onUndoDismiss?: (artifactId: string) => void;
};

export function RunResultPanel({
  artifact,
  title,
  compact = false,
  continueLabel,
  onContinue,
  onApplyManualEdit,
  onDismissReviewRow,
  onUndoDismiss,
}: RunResultPanelProps) {
  const reviewRows = artifact.reviewRows ?? [];
  const dismissedCount = artifact.dismissedReviewRows?.length ?? 0;
  const hasReviewRows = reviewRows.length > 0;
  const isEditable = Boolean(
    onApplyManualEdit && onDismissReviewRow && onUndoDismiss,
  );
  // Captured on mount (the panel is keyed per run) so that clearing the last
  // row lands on the "all clear" confirmation instead of the tab vanishing.
  const [startedFlagged] = useState(hasReviewRows);
  const showAttentionTab = isEditable && (startedFlagged || dismissedCount > 0);
  const [previewMode, setPreviewMode] = useState<PreviewMode>(
    hasReviewRows ? "review" : "worksheet",
  );
  const { columnDefs, rowData } = buildGridModel(artifact.workbookPreview);
  const activeMode = showAttentionTab ? previewMode : "worksheet";

  return (
    <section className="result-panel">
      <header className="result-panel-header">
        <div className="result-panel-heading">
          <span className={hasReviewRows ? "result-dot warning" : "result-dot"} />
          <h2>{title}</h2>
        </div>
        <a className="ghost-button" href={artifact.workbookDownloadUrl}>
          <DownloadIcon />
          Workbook
        </a>
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
            className={hasReviewRows ? "stat-tile warning" : "stat-tile"}
          >
            <span>Needs attention</span>
            <strong>{reviewRows.length}</strong>
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

        {showAttentionTab ? (
          <div
            className="preview-switcher"
            role="tablist"
            aria-label="Preview views"
          >
            <button
              type="button"
              role="tab"
              aria-selected={activeMode === "worksheet"}
              className={
                activeMode === "worksheet"
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
              aria-selected={activeMode === "review"}
              className={
                activeMode === "review"
                  ? hasReviewRows
                    ? "preview-toggle active warning"
                    : "preview-toggle active"
                  : "preview-toggle"
              }
              onClick={() => setPreviewMode("review")}
            >
              {hasReviewRows ? (
                <>
                  <AlertIcon size={12} />
                  Needs attention ({reviewRows.length})
                </>
              ) : (
                <>
                  <CheckIcon size={12} />
                  All clear
                </>
              )}
            </button>
          </div>
        ) : null}
      </div>

      <div
        className={compact ? "grid-shell compact" : "grid-shell"}
        aria-label={activeMode === "review" ? "review rows" : "sheet preview"}
      >
        {activeMode === "review" && isEditable ? (
          <NeedsAttentionList
            artifact={artifact}
            onApply={(reviewRow, rowNumber, value) =>
              onApplyManualEdit!(artifact.id, reviewRow, rowNumber, value)
            }
            onDismiss={(reviewRow) =>
              onDismissReviewRow!(artifact.id, reviewRow)
            }
            onUndoDismiss={() => onUndoDismiss!(artifact.id)}
          />
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
              ? `${reviewRows.length} bill${reviewRows.length === 1 ? " still needs" : "s still need"} attention — fix or delete for a clean start.`
              : "Everything in this stage is resolved."}
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

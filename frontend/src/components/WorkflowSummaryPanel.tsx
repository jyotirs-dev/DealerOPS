import type { CurrentWorkbook, WorkflowArtifact } from "../workflowTypes";

type WorkflowSummaryPanelProps = {
  currentWorkbook: CurrentWorkbook | null;
  artifacts: WorkflowArtifact[];
  onOpenReview: () => void;
};

const STAGE_LABELS = {
  convert: "Stage 1",
  rto: "Stage 2",
  insurance: "Stage 3",
} as const;

export function WorkflowSummaryPanel({
  currentWorkbook,
  artifacts,
  onOpenReview,
}: WorkflowSummaryPanelProps) {
  const orderedArtifacts = [...artifacts].sort(
    (left, right) => left.completedOrder - right.completedOrder,
  );

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <div>
          <p className="eyebrow">Workflow snapshot</p>
          <h2>{currentWorkbook ? "Current workbook ready" : "No workbook yet"}</h2>
        </div>
        {artifacts.length > 0 ? (
          <button
            type="button"
            className="secondary-button"
            onClick={onOpenReview}
          >
            Open Review & Download
          </button>
        ) : null}
      </div>

      <div className="workflow-support-card">
        <div className="workflow-support-row">
          <span className="workflow-support-label">Current workbook</span>
          <strong>{currentWorkbook?.fileName ?? "Awaiting stage output"}</strong>
        </div>
        {currentWorkbook?.preview ? (
          <div className="preview-meta">
            <span>{currentWorkbook.preview.sheetTitle}</span>
            <span>{currentWorkbook.preview.headerRow.length} columns</span>
            <span>{currentWorkbook.preview.rows.length} rows</span>
          </div>
        ) : null}
      </div>

      <div className="artifact-timeline">
        <div className="artifact-timeline-header">
          <h3>Completed artifacts</h3>
          <p className="process-note">
            Every successful stage creates a workbook artifact. The full preview
            and downloads stay in the Review & Download tab.
          </p>
        </div>

        {orderedArtifacts.length > 0 ? (
          <div className="artifact-card-list">
            {orderedArtifacts.map((artifact) => (
              <article key={artifact.id} className="artifact-card">
                <div className="artifact-card-topline">
                  <span className="stage-status-pill completed">
                    {STAGE_LABELS[artifact.stage]}
                  </span>
                  <strong>{artifact.displayLabel}</strong>
                </div>
                <p className="artifact-file-name">{artifact.workbookFileName}</p>
                <p className="artifact-source-line">
                  Source workbook: {artifact.sourceWorkbookFileName}
                </p>
                {artifact.reviewRows?.length ? (
                  <p className="artifact-review-note">
                    {artifact.reviewRows.length} review row
                    {artifact.reviewRows.length === 1 ? "" : "s"} flagged.
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-grid workflow-empty-state">
            Complete stage 1 or upload a workbook override in later stages to
            start building workflow artifacts.
          </div>
        )}
      </div>
    </div>
  );
}

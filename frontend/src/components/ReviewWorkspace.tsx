import type { WorkflowArtifact, WorkflowStageId } from "../workflowTypes";
import { RunResultPanel } from "./RunResultPanel";
import { DownloadIcon } from "./icons";

const STAGE_BADGES: Record<WorkflowStageId, string> = {
  convert: "Stage 1",
  rto: "Stage 2",
  insurance: "Stage 3",
};

type ReviewWorkspaceProps = {
  artifacts: WorkflowArtifact[];
  selectedArtifactId: string | null;
  onSelectArtifact: (artifactId: string) => void;
};

export function ReviewWorkspace({
  artifacts,
  selectedArtifactId,
  onSelectArtifact,
}: ReviewWorkspaceProps) {
  const orderedArtifacts = [...artifacts].sort(
    (left, right) => right.completedOrder - left.completedOrder,
  );
  const selectedArtifact =
    orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId)
    ?? orderedArtifacts[0]
    ?? null;
  const latestArtifact = orderedArtifacts[0] ?? null;

  if (!selectedArtifact || !latestArtifact) {
    return (
      <div className="empty-grid workflow-empty-state">
        No completed stages yet. Finish Stage 1, or run a later stage with your
        own workbook, to start building outputs here.
      </div>
    );
  }

  return (
    <div className="review-layout">
      <div className="artifact-history">
        {orderedArtifacts.map((artifact) => (
          <button
            key={artifact.id}
            type="button"
            className={
              selectedArtifact.id === artifact.id
                ? "artifact-card active"
                : "artifact-card"
            }
            aria-pressed={selectedArtifact.id === artifact.id}
            onClick={() => onSelectArtifact(artifact.id)}
          >
            <span className="artifact-card-topline">
              <span className="artifact-stage-badge">
                {STAGE_BADGES[artifact.stage]}
              </span>
              <strong>{artifact.displayLabel}</strong>
            </span>
            <span className="artifact-file-name">
              {artifact.workbookFileName}
            </span>
            {artifact.reviewRows?.length ? (
              <span className="artifact-review-note">
                {artifact.reviewRows.length} flagged for review
              </span>
            ) : null}
          </button>
        ))}

        <div className="final-export">
          <strong>Final export</strong>
          <a className="success-button" href={latestArtifact.workbookDownloadUrl}>
            <DownloadIcon size={14} />
            Download final workbook
          </a>
          <span className="process-note">
            Latest output: {latestArtifact.workbookFileName}
          </span>
        </div>
      </div>

      <RunResultPanel
        key={selectedArtifact.id}
        artifact={selectedArtifact}
        title={selectedArtifact.displayLabel}
      />
    </div>
  );
}

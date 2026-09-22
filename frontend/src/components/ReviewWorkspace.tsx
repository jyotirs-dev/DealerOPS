import { useState } from "react";

import type { WorkflowArtifact, WorkflowStageId } from "../workflowTypes";
import { ReviewExportPanel } from "./ReviewExportPanel";
import { AlertIcon } from "./icons";

const STAGE_BADGES: Record<WorkflowStageId, string> = {
  convert: "Stage 1",
  rto: "Stage 2",
  insurance: "Stage 3",
};

type ReviewWorkspaceProps = {
  artifacts: WorkflowArtifact[];
  selectedArtifactId: string | null;
  onSelectArtifact: (artifactId: string) => void;
  onOpenStage: (stage: WorkflowStageId) => void;
};

export function ReviewWorkspace({
  artifacts,
  selectedArtifactId,
  onSelectArtifact,
  onOpenStage,
}: ReviewWorkspaceProps) {
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  const orderedArtifacts = [...artifacts].sort(
    (left, right) => right.completedOrder - left.completedOrder,
  );
  const latestArtifact = orderedArtifacts[0] ?? null;
  const selectedArtifact =
    orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId)
    ?? latestArtifact;

  if (!selectedArtifact || !latestArtifact) {
    return (
      <div className="empty-grid workflow-empty-state">
        No completed stages yet. Finish Stage 1, or run a later stage with your
        own workbook, to start building outputs here.
      </div>
    );
  }

  const unresolved = orderedArtifacts
    .filter((artifact) => (artifact.reviewRows?.length ?? 0) > 0)
    .map((artifact) => ({
      stage: artifact.stage,
      count: artifact.reviewRows?.length ?? 0,
    }));

  return (
    <div className="review-workspace">
      {unresolved.map((entry) => (
        <p className="unresolved-note" key={entry.stage}>
          <AlertIcon size={12} />
          {entry.count} item{entry.count === 1 ? "" : "s"} left unresolved in{" "}
          {STAGE_BADGES[entry.stage]}.
          <button
            type="button"
            className="link-button"
            onClick={() => onOpenStage(entry.stage)}
          >
            {entry.count === 1 ? "Go fix it" : "Go fix them"}
          </button>
        </p>
      ))}

      {orderedArtifacts.length > 1 ? (
        <div className="history-toggle-row">
          <button
            type="button"
            className="history-toggle-link"
            onClick={() => setIsHistoryOpen((open) => !open)}
          >
            {selectedArtifact.id === latestArtifact.id
              ? "Viewing latest output"
              : `Viewing ${selectedArtifact.displayLabel}`}
            {" · view earlier stage "}
            {isHistoryOpen ? "▲" : "▾"}
          </button>

          {isHistoryOpen ? (
            <div className="history-pill-row">
              {orderedArtifacts.map((artifact) => (
                <button
                  key={artifact.id}
                  type="button"
                  className={
                    selectedArtifact.id === artifact.id
                      ? "history-pill active"
                      : "history-pill"
                  }
                  onClick={() => {
                    onSelectArtifact(artifact.id);
                    setIsHistoryOpen(false);
                  }}
                >
                  {STAGE_BADGES[artifact.stage]} · {artifact.displayLabel}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <ReviewExportPanel
        key={selectedArtifact.id}
        artifact={selectedArtifact}
      />
    </div>
  );
}

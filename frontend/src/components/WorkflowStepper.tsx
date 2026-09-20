import type { StageState, WorkflowTabId, WorkingFile } from "../workflowTypes";
import { WORKING_FILE_ORIGIN_LABELS } from "../workflowTypes";
import { AlertIcon, CheckIcon, SettingsIcon } from "./icons";

export type StepperStage = {
  id: WorkflowTabId;
  label: string;
  state: StageState;
  statusText: string;
};

type WorkflowStepperProps = {
  stages: StepperStage[];
  activeStage: WorkflowTabId;
  workingFile: WorkingFile | null;
  onSelectStage: (stage: WorkflowTabId) => void;
  onOpenSettings: () => void;
};

function StepMarker({ state, step }: { state: StageState; step: number }) {
  if (state === "completed") {
    return (
      <span className="step-marker completed">
        <CheckIcon />
      </span>
    );
  }
  if (state === "attention") {
    return (
      <span className="step-marker attention">
        <AlertIcon size={13} />
      </span>
    );
  }
  if (state === "working") {
    return (
      <span className="step-marker working">
        <span className="step-pulse" />
      </span>
    );
  }
  return <span className={`step-marker ${state}`}>{step}</span>;
}

export function WorkflowStepper({
  stages,
  activeStage,
  workingFile,
  onSelectStage,
  onOpenSettings,
}: WorkflowStepperProps) {
  return (
    <aside className="workflow-rail" aria-label="Workflow overview">
      <div className="rail-brand">
        <span className="rail-brand-name">DealerOPS</span>
        <span className="rail-brand-sub">Invoice &amp; bill workflow</span>
      </div>

      <div className={workingFile ? "rail-file" : "rail-file empty"}>
        <span className="rail-file-label">Working file</span>
        {workingFile ? (
          <>
            <strong className="rail-file-name">{workingFile.fileName}</strong>
            <span className="rail-file-origin">
              {WORKING_FILE_ORIGIN_LABELS[workingFile.origin]}
            </span>
          </>
        ) : (
          <span className="rail-file-origin">
            Generate one in Stage 1, or upload your own to resume mid-workflow.
          </span>
        )}
      </div>

      <nav className="rail-steps" aria-label="Workflow stages">
        {stages.map((stage, index) => (
          <button
            key={stage.id}
            type="button"
            className={
              activeStage === stage.id ? "rail-step active" : "rail-step"
            }
            aria-current={activeStage === stage.id ? "step" : undefined}
            onClick={() => onSelectStage(stage.id)}
          >
            <span className="rail-step-marker-column">
              <StepMarker state={stage.state} step={index + 1} />
              {index < stages.length - 1 ? (
                <span className="rail-step-connector" />
              ) : null}
            </span>
            <span className="rail-step-body">
              <span className="rail-step-label">{stage.label}</span>
              <span className={`rail-step-status ${stage.state}`}>
                {stage.statusText}
              </span>
            </span>
          </button>
        ))}
      </nav>

      <button type="button" className="rail-settings" onClick={onOpenSettings}>
        <SettingsIcon />
        Extraction settings
      </button>
    </aside>
  );
}

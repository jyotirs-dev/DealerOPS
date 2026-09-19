import type { ChangeEvent } from "react";

import type {
  Settings,
  UpdateStageId,
  WorkbookOverrideState,
} from "../workflowTypes";

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

type ConvertStagePanelProps = {
  rawFile: File | null;
  isProcessing: boolean;
  error: string | null;
  onRawFileChange: (file: File | null) => void;
  onRun: () => void;
};

export function ConvertStagePanel({
  rawFile,
  isProcessing,
  error,
  onRawFileChange,
  onRun,
}: ConvertStagePanelProps) {
  return (
    <div className="tab-card">
      <h2>Stage 1: Convert raw export</h2>
      <p className="tab-hint">
        Upload the OEM / DMS raw invoice export and generate the styled Vehicle
        Sales Register workbook with formulas.
      </p>

      <div className="upload-stack">
        <label className="field-label" htmlFor="convert-upload">
          Upload raw invoice export
        </label>
        <input
          id="convert-upload"
          name="convert-upload"
          type="file"
          accept=".xlsx,.xlsm"
          onChange={(event) => onRawFileChange(event.target.files?.[0] ?? null)}
        />
        <div className="status-chip-row">
          <span className="status-chip">
            File: {rawFile ? rawFile.name : "Not loaded"}
          </span>
        </div>
      </div>

      <div className="action-row">
        <button
          type="button"
          className="primary-button"
          onClick={onRun}
          disabled={!rawFile || isProcessing}
        >
          {isProcessing ? "Generating workbook..." : "Generate styled workbook"}
        </button>
        <p className="process-note">
          This creates the base workbook used by the downstream RTO and
          insurance update stages.
        </p>
      </div>

      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

type AdvancedSettingsPanelProps = {
  settings: Settings;
  onSettingsChange: (key: keyof Settings, value: string | boolean) => void;
};

export function AdvancedSettingsPanel({
  settings,
  onSettingsChange,
}: AdvancedSettingsPanelProps) {
  return (
    <details className="advanced-panel">
      <summary>Advanced parser settings</summary>
      <div className="advanced-grid">
        <label>
          Customer labels
          <input
            type="text"
            value={settings.customerLabels}
            onChange={(event) =>
              onSettingsChange("customerLabels", event.target.value)
            }
          />
        </label>
        <label>
          Amount labels
          <input
            type="text"
            value={settings.amountLabels}
            onChange={(event) =>
              onSettingsChange("amountLabels", event.target.value)
            }
          />
        </label>
        <label>
          Amount position
          <select
            value={settings.amountPosition}
            onChange={(event) =>
              onSettingsChange(
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
              onSettingsChange("nameThreshold", event.target.value)
            }
          />
        </label>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={settings.clearExisting}
            onChange={(event) =>
              onSettingsChange("clearExisting", event.target.checked)
            }
          />
          Clear existing values in the targeted column before writing matches
        </label>
      </div>
    </details>
  );
}

type UpdateStagePanelProps = {
  stageId: UpdateStageId;
  title: string;
  hint: string;
  receiptFiles: File[];
  overrideState: WorkbookOverrideState;
  currentWorkbookName: string | null;
  currentWorkbookStageLabel: string | null;
  effectiveWorkbookName: string | null;
  effectiveWorkbookSource: string | null;
  isProcessing: boolean;
  error: string | null;
  readinessMessage: string;
  canRun: boolean;
  settings: Settings;
  onSettingsChange: (key: keyof Settings, value: string | boolean) => void;
  onReceiptFilesChange: (files: File[]) => void;
  onOverrideWorkbookChange: (file: File | null) => void;
  onClearOverride: () => void;
  onRun: () => void;
};

export function UpdateStagePanel({
  stageId,
  title,
  hint,
  receiptFiles,
  overrideState,
  currentWorkbookName,
  currentWorkbookStageLabel,
  effectiveWorkbookName,
  effectiveWorkbookSource,
  isProcessing,
  error,
  readinessMessage,
  canRun,
  settings,
  onSettingsChange,
  onReceiptFilesChange,
  onOverrideWorkbookChange,
  onClearOverride,
  onRun,
}: UpdateStagePanelProps) {
  const receiptLabel =
    stageId === "rto" ? "Upload RTO receipts" : "Upload insurance files";
  const receiptAccept =
    ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp";
  const buttonLabel =
    stageId === "rto" ? "Update RTO workbook" : "Update insurance workbook";

  return (
    <>
      <div className="tab-card">
        <h2>{title}</h2>
        <p className="tab-hint">{hint}</p>

        <div className="workflow-support-card">
          <div className="workflow-support-row">
            <span className="workflow-support-label">Latest workbook</span>
            <strong>{currentWorkbookName ?? "None yet"}</strong>
          </div>
          <p className="process-note">
            {currentWorkbookName && currentWorkbookStageLabel
              ? `Carried forward from ${currentWorkbookStageLabel}.`
              : "No carried-forward workbook yet. Upload a workbook override to resume this stage directly."}
          </p>
        </div>

        <div className="upload-stack">
          <label className="field-label" htmlFor={`${stageId}-override`}>
            Optional workbook override
          </label>
          <input
            id={`${stageId}-override`}
            name={`${stageId}-override`}
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(event) =>
              onOverrideWorkbookChange(event.target.files?.[0] ?? null)
            }
          />
          <div className="status-chip-row">
            <span className="status-chip">
              Override: {overrideState.fileName ?? "Not loaded"}
            </span>
            {effectiveWorkbookName ? (
              <span className="status-chip">
                Using: {effectiveWorkbookName}
              </span>
            ) : null}
            {effectiveWorkbookSource ? (
              <span className="status-chip">{effectiveWorkbookSource}</span>
            ) : null}
          </div>
          {overrideState.fileName ? (
            <button
              type="button"
              className="secondary-button"
              onClick={onClearOverride}
            >
              Clear workbook override
            </button>
          ) : null}
          {overrideState.error ? (
            <p className="error-banner" role="alert">
              {overrideState.error}
            </p>
          ) : null}
        </div>

        <div className="upload-stack">
          <label className="field-label" htmlFor={`${stageId}-receipts`}>
            {receiptLabel}
          </label>
          <input
            id={`${stageId}-receipts`}
            name={`${stageId}-receipts`}
            type="file"
            accept={receiptAccept}
            multiple
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              onReceiptFilesChange(fileListToArray(event.target.files))
            }
          />
          <span className="status-chip">{receiptFiles.length} files selected</span>
          {renderFileList(receiptFiles)}
        </div>
      </div>

      <AdvancedSettingsPanel
        settings={settings}
        onSettingsChange={onSettingsChange}
      />

      <div className="action-row">
        <button
          type="button"
          className="primary-button"
          onClick={onRun}
          disabled={!canRun}
        >
          {isProcessing ? "Processing workbook..." : buttonLabel}
        </button>
        <p className="process-note">{readinessMessage}</p>
        <p className="process-note">
          The updated workbook and any review rows will appear in Review &
          Download after this stage completes.
        </p>
      </div>

      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}

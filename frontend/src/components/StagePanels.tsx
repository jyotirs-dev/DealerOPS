import { useEffect, useState } from "react";

import { FIXED_HEADERS } from "../lib/workbook";
import type { UpdateStageId, WorkflowArtifact, WorkingFile } from "../workflowTypes";
import { WORKING_FILE_ORIGIN_LABELS } from "../workflowTypes";
import { FileDropZone } from "./FileDropZone";
import { ArrowRightIcon, CheckIcon, FileIcon } from "./icons";

type StageHeaderProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function StageHeader({ eyebrow, title, description }: StageHeaderProps) {
  return (
    <header className="stage-header">
      <span className="stage-eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  );
}

type PriorStageBarProps = {
  artifact: WorkflowArtifact;
  detail: string;
  onOpen: () => void;
};

export function PriorStageBar({ artifact, detail, onOpen }: PriorStageBarProps) {
  return (
    <div className="prior-stage-bar">
      <span className="prior-stage-check">
        <CheckIcon size={15} />
      </span>
      <div className="prior-stage-copy">
        <strong>
          {artifact.displayLabel} — {artifact.workbookFileName}
        </strong>
        <span>{detail}</span>
      </div>
      <button type="button" className="link-button" onClick={onOpen}>
        View result
      </button>
    </div>
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
    <section className="stage-card">
      <FileDropZone
        id="convert-upload"
        label="Upload raw invoice export"
        accept=".xlsx,.xlsm"
        hint="XLSX or XLSM — the raw OEM / DMS export"
        files={rawFile ? [rawFile] : []}
        onFilesChange={(files) => onRawFileChange(files[0] ?? null)}
      />

      <div className="stage-divider" />

      <div className="stage-action-row">
        <button
          type="button"
          className="primary-button"
          onClick={onRun}
          disabled={!rawFile || isProcessing}
        >
          {isProcessing ? "Generating workbook…" : "Generate styled workbook"}
          {isProcessing ? null : <ArrowRightIcon />}
        </button>
        <span className="process-note">
          {rawFile
            ? "Creates the base workbook that Stages 2 and 3 update."
            : "Upload a raw export to continue."}
        </span>
      </div>

      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

type UpdateStagePanelProps = {
  stageId: UpdateStageId;
  workingFile: WorkingFile | null;
  workingFileError: string | null;
  receiptFiles: File[];
  isProcessing: boolean;
  error: string | null;
  readinessMessage: string;
  canRun: boolean;
  onReplaceWorkingFile: (file: File | null) => void;
  onReceiptFilesChange: (files: File[]) => void;
  onRun: () => void;
};

export function UpdateStagePanel({
  stageId,
  workingFile,
  workingFileError,
  receiptFiles,
  isProcessing,
  error,
  readinessMessage,
  canRun,
  onReplaceWorkingFile,
  onReceiptFilesChange,
  onRun,
}: UpdateStagePanelProps) {
  const [isReplacing, setIsReplacing] = useState(false);
  const showPicker = isReplacing || !workingFile;

  useEffect(() => {
    if (workingFile && !workingFileError) {
      setIsReplacing(false);
    }
  }, [workingFile, workingFileError]);

  const receiptLabel =
    stageId === "rto" ? "Upload RTO receipts" : "Upload insurance bills";
  const buttonLabel =
    stageId === "rto" ? "Update RTO amounts" : "Update insurance amounts";

  return (
    <section className="stage-card">
      <div className="working-file-row">
        <div className="working-file-identity">
          <span className="working-file-icon">
            <FileIcon />
          </span>
          <div>
            <span className="working-file-caption">Working file</span>
            <strong className="working-file-name">
              {workingFile ? workingFile.fileName : "No workbook yet"}
            </strong>
            <span className="working-file-origin">
              {workingFile
                ? WORKING_FILE_ORIGIN_LABELS[workingFile.origin]
                : "Generate one in Stage 1, or upload one to resume here."}
            </span>
          </div>
        </div>
        {workingFile ? (
          <button
            type="button"
            className="secondary-button"
            onClick={() => setIsReplacing((current) => !current)}
          >
            {isReplacing ? "Keep current file" : "Use a different file"}
          </button>
        ) : null}
      </div>

      <div className="target-column-row">
        <span className="target-column-caption">Target columns</span>
        <span className="target-chip">{FIXED_HEADERS.customer}</span>
        <span className="target-chip">{FIXED_HEADERS.insurance}</span>
        <span className="target-chip">{FIXED_HEADERS.rto}</span>
      </div>

      {showPicker ? (
        <FileDropZone
          id={`${stageId}-workbook`}
          label={workingFile ? "Replace working file" : "Upload a workbook"}
          accept=".xlsx,.xlsm"
          hint="XLSX or XLSM containing the target columns above"
          files={[]}
          onFilesChange={(files) => {
            onReplaceWorkingFile(files[0] ?? null);
          }}
        />
      ) : null}

      {workingFileError ? (
        <p className="error-banner" role="alert">
          {workingFileError}
        </p>
      ) : null}

      <div className="stage-divider" />

      <FileDropZone
        id={`${stageId}-receipts`}
        label={receiptLabel}
        accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
        hint="PDF, PNG, JPG, TIFF — multiple files supported"
        files={receiptFiles}
        multiple
        onFilesChange={onReceiptFilesChange}
      />

      <div className="stage-divider" />

      <div className="stage-action-row">
        <button
          type="button"
          className="primary-button"
          onClick={onRun}
          disabled={!canRun}
        >
          {isProcessing ? "Processing workbook…" : buttonLabel}
          {isProcessing ? null : <ArrowRightIcon />}
        </button>
        <span className="process-note">{readinessMessage}</span>
      </div>

      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

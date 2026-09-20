import { useState } from "react";

import { readWorkbookPreview } from "./lib/workbook";
import type { WorkbookPreview } from "./lib/workbook";
import { ReviewWorkspace } from "./components/ReviewWorkspace";
import { RunResultPanel } from "./components/RunResultPanel";
import { WorkflowStepper } from "./components/WorkflowStepper";
import type { StepperStage } from "./components/WorkflowStepper";
import {
  ConvertStagePanel,
  PriorStageBar,
  StageHeader,
  UpdateStagePanel,
} from "./components/StagePanels";
import {
  DEFAULT_SETTINGS,
  ExtractionSettingsDrawer,
} from "./components/ExtractionSettingsDrawer";
import type {
  ProcessResponse,
  SalesRegisterResponse,
  Settings,
  UpdateStageId,
  WorkflowArtifact,
  WorkflowStageId,
  WorkflowTabId,
  WorkingFile,
} from "./workflowTypes";

const STAGE_COPY: Record<
  WorkflowTabId,
  { eyebrow: string; title: string; description: string; railLabel: string }
> = {
  convert: {
    eyebrow: "Stage 1 of 4",
    title: "Convert raw export",
    description:
      "Upload the OEM / DMS raw invoice export and generate the styled Vehicle Sales Register workbook with formulas.",
    railLabel: "Stage 1 · Convert",
  },
  rto: {
    eyebrow: "Stage 2 of 4",
    title: "Update RTO amounts",
    description:
      "Match RTO receipts to sales rows and write the confirmed amounts into the working file. Nothing here changes insurance data.",
    railLabel: "Stage 2 · Update RTO",
  },
  insurance: {
    eyebrow: "Stage 3 of 4",
    title: "Update insurance amounts",
    description:
      "Match insurance bills to sales rows and write the confirmed amounts into the working file. Nothing here changes RTO data.",
    railLabel: "Stage 3 · Update Insurance",
  },
  review: {
    eyebrow: "All outputs",
    title: "Review & export",
    description:
      "Every completed stage stays here as a downloadable output. Compare results, check flagged rows, and export the final workbook.",
    railLabel: "Review & Export",
  },
};

const STAGE_NEXT_TAB: Record<WorkflowStageId, WorkflowTabId> = {
  convert: "rto",
  rto: "insurance",
  insurance: "review",
};

const CONTINUE_LABELS: Record<WorkflowStageId, string> = {
  convert: "Continue to Stage 2",
  rto: "Continue to Stage 3",
  insurance: "Continue to review",
};

function previewFromProcessResponse(
  result: ProcessResponse,
  fileName: string,
): WorkbookPreview {
  return {
    fileName,
    sheetTitle: result.sheetTitle,
    headerRow: result.headerRow,
    rows: result.rows,
  };
}

function extractDownloadFileName(url: string, fallbackName: string): string {
  const cleaned = url.split("?")[0] ?? "";
  const parts = cleaned.split("/").filter(Boolean);
  const fileName = parts[parts.length - 1];
  return fileName || fallbackName;
}

async function hydrateDownloadedWorkbook(
  downloadUrl: string,
  fallbackName: string,
  previewFallback: WorkbookPreview | null = null,
): Promise<{ file: File; preview: WorkbookPreview | null; fileName: string }> {
  const workbookResponse = await fetch(downloadUrl);
  if (!workbookResponse.ok) {
    throw new Error("Failed to load generated workbook.");
  }

  const workbookBlob = await workbookResponse.blob();
  const fileName = extractDownloadFileName(downloadUrl, fallbackName);
  const file = new File([workbookBlob], fileName, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

  try {
    const preview = await readWorkbookPreview(file);
    return { file, preview, fileName };
  } catch {
    return { file, preview: previewFallback, fileName };
  }
}

function nextCompletedOrder(artifacts: WorkflowArtifact[]): number {
  return (
    artifacts.reduce(
      (currentMax, artifact) => Math.max(currentMax, artifact.completedOrder),
      0,
    ) + 1
  );
}

function mergeArtifacts(
  artifacts: WorkflowArtifact[],
  artifact: WorkflowArtifact,
  invalidatedStages: WorkflowStageId[] = [],
): WorkflowArtifact[] {
  return [
    ...artifacts.filter(
      (entry) =>
        entry.stage !== artifact.stage
        && !invalidatedStages.includes(entry.stage),
    ),
    artifact,
  ].sort((left, right) => left.completedOrder - right.completedOrder);
}

function describeArtifact(artifact: WorkflowArtifact): string {
  if (artifact.summary) {
    return `${artifact.summary.billsUpdated} values updated · ${artifact.summary.billsReview} flagged for review`;
  }
  return `${artifact.rowsWritten ?? 0} rows written · detected month ${artifact.monthYear || "unknown"}`;
}

export default function App() {
  const [activeStage, setActiveStage] = useState<WorkflowTabId>("convert");
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [workingFile, setWorkingFile] = useState<WorkingFile | null>(null);
  const [workingFileError, setWorkingFileError] = useState<string | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(
    null,
  );

  const [rawInvoiceFile, setRawInvoiceFile] = useState<File | null>(null);
  const [convertError, setConvertError] = useState<string | null>(null);
  const [isGeneratingWorkbook, setIsGeneratingWorkbook] = useState(false);

  const [rtoFiles, setRtoFiles] = useState<File[]>([]);
  const [rtoError, setRtoError] = useState<string | null>(null);
  const [isProcessingRto, setIsProcessingRto] = useState(false);

  const [insuranceFiles, setInsuranceFiles] = useState<File[]>([]);
  const [insuranceError, setInsuranceError] = useState<string | null>(null);
  const [isProcessingInsurance, setIsProcessingInsurance] = useState(false);

  const convertArtifact =
    artifacts.find((artifact) => artifact.stage === "convert") ?? null;
  const rtoArtifact =
    artifacts.find((artifact) => artifact.stage === "rto") ?? null;
  const insuranceArtifact =
    artifacts.find((artifact) => artifact.stage === "insurance") ?? null;

  function handleSettingsChange(
    key: keyof Settings,
    value: string | boolean,
  ) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  async function handleReplaceWorkingFile(file: File | null) {
    if (!file) {
      return;
    }

    setWorkingFileError(null);
    try {
      const preview = await readWorkbookPreview(file);
      setWorkingFile({
        file,
        preview,
        fileName: file.name,
        origin: "upload",
      });
    } catch (error) {
      setWorkingFileError(
        error instanceof Error ? error.message : "Failed to read workbook.",
      );
    }
  }

  async function handleGenerateSalesRegister() {
    if (!rawInvoiceFile || isGeneratingWorkbook) {
      return;
    }

    const formData = new FormData();
    formData.append("raw_file", rawInvoiceFile);

    setIsGeneratingWorkbook(true);
    setConvertError(null);

    try {
      const response = await fetch("/api/generate-sales-register", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.error ?? "Generation failed.");
      }

      const result = payload as SalesRegisterResponse;
      const fallbackFileName = `SalesRegister_${result.monthYear || "generated"}.xlsx`;
      const workbook = await hydrateDownloadedWorkbook(
        result.downloadUrl,
        fallbackFileName,
      );

      const completedOrder = nextCompletedOrder(artifacts);
      const artifact: WorkflowArtifact = {
        id: `convert-${completedOrder}`,
        stage: "convert",
        displayLabel: "Generated workbook",
        workbookDownloadUrl: result.downloadUrl,
        workbookFile: workbook.file,
        workbookPreview: workbook.preview,
        workbookFileName: workbook.fileName,
        sourceWorkbookFileName: rawInvoiceFile.name,
        reviewRows: [],
        monthYear: result.monthYear,
        rowsWritten: result.rowsWritten,
        manualColumns: result.manualColumns,
        completedOrder,
      };

      setArtifacts(mergeArtifacts(artifacts, artifact, ["rto", "insurance"]));
      setWorkingFile({
        file: workbook.file,
        preview: workbook.preview,
        fileName: workbook.fileName,
        origin: "convert",
        downloadUrl: result.downloadUrl,
      });
      setSelectedArtifactId(artifact.id);
      setWorkingFileError(null);
      setRtoFiles([]);
      setInsuranceFiles([]);
      setRtoError(null);
      setInsuranceError(null);
    } catch (error) {
      setConvertError(
        error instanceof Error ? error.message : "Generation failed.",
      );
    } finally {
      setIsGeneratingWorkbook(false);
    }
  }

  async function handleProcessStage(stageId: UpdateStageId) {
    const isRto = stageId === "rto";
    const receiptFiles = isRto ? rtoFiles : insuranceFiles;
    const setError = isRto ? setRtoError : setInsuranceError;
    const setProcessing = isRto ? setIsProcessingRto : setIsProcessingInsurance;

    if (!workingFile || receiptFiles.length === 0) {
      return;
    }

    const formData = new FormData();
    formData.append("workbook", workingFile.file);
    receiptFiles.forEach((file) =>
      formData.append(isRto ? "rto_files[]" : "insurance_files[]", file),
    );
    formData.append("customer_labels", settings.customerLabels);
    formData.append("amount_labels", settings.amountLabels);
    formData.append("amount_position", settings.amountPosition);
    formData.append("name_threshold", settings.nameThreshold);
    formData.append("clear_existing", settings.clearExisting ? "1" : "0");

    setProcessing(true);
    setError(null);

    try {
      const response = await fetch("/api/process", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.error ?? "Processing failed.");
      }

      const result = {
        ...((payload ?? {}) as Omit<ProcessResponse, "reviewRows">),
        reviewRows: Array.isArray(payload?.reviewRows) ? payload.reviewRows : [],
      } as ProcessResponse;
      const fallbackFileName = extractDownloadFileName(
        result.downloadUrl,
        `${stageId}_updated.xlsx`,
      );
      const workbook = await hydrateDownloadedWorkbook(
        result.downloadUrl,
        fallbackFileName,
        previewFromProcessResponse(result, fallbackFileName),
      );

      const completedOrder = nextCompletedOrder(artifacts);
      const artifact: WorkflowArtifact = {
        id: `${stageId}-${completedOrder}`,
        stage: stageId,
        displayLabel: isRto
          ? "RTO updated workbook"
          : "Insurance updated workbook",
        workbookDownloadUrl: result.downloadUrl,
        workbookFile: workbook.file,
        workbookPreview: workbook.preview,
        workbookFileName: workbook.fileName,
        sourceWorkbookFileName: workingFile.fileName,
        reviewCsvUrl: result.reviewCsvUrl,
        summary: result.summary,
        reviewRows: result.reviewRows,
        completedOrder,
      };

      const invalidatedStages: WorkflowStageId[] = isRto ? ["insurance"] : [];
      setArtifacts(mergeArtifacts(artifacts, artifact, invalidatedStages));
      setWorkingFile({
        file: workbook.file,
        preview: workbook.preview,
        fileName: workbook.fileName,
        origin: stageId,
        downloadUrl: result.downloadUrl,
      });
      setSelectedArtifactId(artifact.id);

      if (isRto) {
        setRtoFiles([]);
        setInsuranceFiles([]);
      } else {
        setInsuranceFiles([]);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "Processing failed.");
    } finally {
      setProcessing(false);
    }
  }

  function buildUpdateStage(stageId: UpdateStageId): StepperStage {
    const artifact = stageId === "rto" ? rtoArtifact : insuranceArtifact;
    const isProcessing =
      stageId === "rto" ? isProcessingRto : isProcessingInsurance;
    const receiptFiles = stageId === "rto" ? rtoFiles : insuranceFiles;

    if (isProcessing) {
      return {
        id: stageId,
        label: STAGE_COPY[stageId].railLabel,
        state: "working",
        statusText: "Working…",
      };
    }
    if (artifact) {
      return {
        id: stageId,
        label: STAGE_COPY[stageId].railLabel,
        state: "completed",
        statusText: artifact.reviewRows?.length
          ? `Completed · ${artifact.reviewRows.length} flagged`
          : "Completed",
      };
    }
    if (!workingFile) {
      return {
        id: stageId,
        label: STAGE_COPY[stageId].railLabel,
        state: "attention",
        statusText: "Needs a working file",
      };
    }
    return {
      id: stageId,
      label: STAGE_COPY[stageId].railLabel,
      state: "ready",
      statusText:
        receiptFiles.length > 0
          ? `${receiptFiles.length} file${receiptFiles.length === 1 ? "" : "s"} ready`
          : "Ready for files",
    };
  }

  const stages: StepperStage[] = [
    {
      id: "convert",
      label: STAGE_COPY.convert.railLabel,
      state: isGeneratingWorkbook
        ? "working"
        : convertArtifact
          ? "completed"
          : rawInvoiceFile
            ? "ready"
            : "waiting",
      statusText: isGeneratingWorkbook
        ? "Working…"
        : convertArtifact
          ? "Completed"
          : rawInvoiceFile
            ? "Ready to run"
            : "Not started",
    },
    buildUpdateStage("rto"),
    buildUpdateStage("insurance"),
    {
      id: "review",
      label: STAGE_COPY.review.railLabel,
      state: artifacts.length > 0 ? "completed" : "waiting",
      statusText:
        artifacts.length > 0
          ? `${artifacts.length} output${artifacts.length === 1 ? "" : "s"}`
          : "Awaiting output",
    },
  ];

  function buildReadinessMessage(stageId: UpdateStageId): string {
    const isProcessing =
      stageId === "rto" ? isProcessingRto : isProcessingInsurance;
    const receiptFiles = stageId === "rto" ? rtoFiles : insuranceFiles;
    const noun = stageId === "rto" ? "RTO receipt" : "insurance bill";

    if (isProcessing) {
      return "Processing workbook…";
    }
    if (!workingFile) {
      return `Generate Stage 1 first, or upload a workbook to resume at ${stageId === "rto" ? "RTO" : "insurance"}.`;
    }
    if (receiptFiles.length === 0) {
      return `Upload at least one ${noun} to continue.`;
    }

    const rowCount = workingFile.preview?.rows.length;
    return rowCount
      ? `Ready to match ${receiptFiles.length} file${receiptFiles.length === 1 ? "" : "s"} against ${rowCount} sales rows.`
      : `Ready to match ${receiptFiles.length} file${receiptFiles.length === 1 ? "" : "s"}.`;
  }

  function renderUpdateStage(stageId: UpdateStageId) {
    const artifact = stageId === "rto" ? rtoArtifact : insuranceArtifact;
    const priorArtifact =
      stageId === "rto" ? convertArtifact : (rtoArtifact ?? convertArtifact);
    const receiptFiles = stageId === "rto" ? rtoFiles : insuranceFiles;
    const isProcessing =
      stageId === "rto" ? isProcessingRto : isProcessingInsurance;
    const canRun =
      Boolean(workingFile) && receiptFiles.length > 0 && !isProcessing;

    return (
      <>
        {priorArtifact ? (
          <PriorStageBar
            artifact={priorArtifact}
            detail={describeArtifact(priorArtifact)}
            onOpen={() => setActiveStage(priorArtifact.stage)}
          />
        ) : null}

        <UpdateStagePanel
          stageId={stageId}
          workingFile={workingFile}
          workingFileError={workingFileError}
          receiptFiles={receiptFiles}
          isProcessing={isProcessing}
          error={stageId === "rto" ? rtoError : insuranceError}
          readinessMessage={buildReadinessMessage(stageId)}
          canRun={canRun}
          onReplaceWorkingFile={(file) => {
            void handleReplaceWorkingFile(file);
          }}
          onReceiptFilesChange={(files) => {
            if (stageId === "rto") {
              setRtoFiles(files);
              setRtoError(null);
            } else {
              setInsuranceFiles(files);
              setInsuranceError(null);
            }
          }}
          onRun={() => {
            void handleProcessStage(stageId);
          }}
        />

        {artifact ? (
          <RunResultPanel
            key={artifact.id}
            artifact={artifact}
            title="Last run result"
            compact
            continueLabel={CONTINUE_LABELS[stageId]}
            onContinue={() => setActiveStage(STAGE_NEXT_TAB[stageId])}
          />
        ) : null}
      </>
    );
  }

  const copy = STAGE_COPY[activeStage];

  return (
    <div className="app-shell">
      <WorkflowStepper
        stages={stages}
        activeStage={activeStage}
        workingFile={workingFile}
        onSelectStage={setActiveStage}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      <main className="stage-region">
        <StageHeader
          eyebrow={copy.eyebrow}
          title={copy.title}
          description={copy.description}
        />

        {activeStage === "convert" ? (
          <>
            <ConvertStagePanel
              rawFile={rawInvoiceFile}
              isProcessing={isGeneratingWorkbook}
              error={convertError}
              onRawFileChange={(file) => {
                setRawInvoiceFile(file);
                setConvertError(null);
              }}
              onRun={() => {
                void handleGenerateSalesRegister();
              }}
            />
            {convertArtifact ? (
              <RunResultPanel
                key={convertArtifact.id}
                artifact={convertArtifact}
                title="Last run result"
                compact
                continueLabel={CONTINUE_LABELS.convert}
                onContinue={() => setActiveStage(STAGE_NEXT_TAB.convert)}
              />
            ) : null}
          </>
        ) : null}

        {activeStage === "rto" ? renderUpdateStage("rto") : null}
        {activeStage === "insurance" ? renderUpdateStage("insurance") : null}

        {activeStage === "review" ? (
          <ReviewWorkspace
            artifacts={artifacts}
            selectedArtifactId={selectedArtifactId}
            onSelectArtifact={setSelectedArtifactId}
          />
        ) : null}
      </main>

      <ExtractionSettingsDrawer
        isOpen={isSettingsOpen}
        settings={settings}
        onSettingsChange={handleSettingsChange}
        onReset={() => setSettings(DEFAULT_SETTINGS)}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
}

import { useEffect, useState } from "react";

import { FIXED_HEADERS, readWorkbookPreview } from "./lib/workbook";
import { ReviewWorkspace } from "./components/ReviewWorkspace";
import { StageTabs } from "./components/StageTabs";
import {
  ConvertStagePanel,
  UpdateStagePanel,
} from "./components/StagePanels";
import { WorkflowSummaryPanel } from "./components/WorkflowSummaryPanel";
import type {
  CurrentWorkbook,
  PreviewMode,
  ProcessResponse,
  SalesRegisterResponse,
  Settings,
  StageTone,
  UpdateStageId,
  WorkflowArtifact,
  WorkflowStageId,
  WorkflowTabId,
  WorkbookOverrideState,
} from "./workflowTypes";
import type { WorkbookPreview } from "./lib/workbook";

const DEFAULT_SETTINGS: Settings = {
  customerLabels: "Insured, Insured Name, Received From",
  amountLabels:
    "Received with Thanks Rs, Grand Total (in Rs), Grand Total, Final Amount, Amount Payable, Net Payable",
  amountPosition: "same_line",
  nameThreshold: "95",
  clearExisting: false,
};

const STAGE_TITLES: Record<WorkflowTabId, string> = {
  convert: "Stage 1: Convert",
  rto: "Stage 2: Update RTO",
  insurance: "Stage 3: Update Insurance",
  review: "Review & Download",
};

const STAGE_LABELS: Record<WorkflowStageId, string> = {
  convert: "Stage 1",
  rto: "Stage 2",
  insurance: "Stage 3",
};

const STAGE_NEXT_TAB: Record<WorkflowStageId, WorkflowTabId> = {
  convert: "rto",
  rto: "insurance",
  insurance: "review",
};

function emptyOverrideState(): WorkbookOverrideState {
  return {
    file: null,
    preview: null,
    error: null,
    fileName: null,
  };
}

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
): Promise<{
  file: File;
  preview: WorkbookPreview | null;
  fileName: string;
}> {
  const workbookResponse = await fetch(downloadUrl);
  if (!workbookResponse.ok) {
    throw new Error("Failed to load generated workbook.");
  }

  const workbookBlob = await workbookResponse.blob();
  const fileName = extractDownloadFileName(downloadUrl, fallbackName);
  const file = new File([workbookBlob], fileName, {
    type:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        entry.stage !== artifact.stage && !invalidatedStages.includes(entry.stage),
    ),
    artifact,
  ].sort((left, right) => left.completedOrder - right.completedOrder);
}

type StageStatus = {
  text: string;
  tone: StageTone;
};

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkflowTabId>("convert");
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [currentWorkbook, setCurrentWorkbook] = useState<CurrentWorkbook | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("worksheet");

  const [rawInvoiceFile, setRawInvoiceFile] = useState<File | null>(null);
  const [convertError, setConvertError] = useState<string | null>(null);
  const [isGeneratingWorkbook, setIsGeneratingWorkbook] = useState(false);

  const [rtoFiles, setRtoFiles] = useState<File[]>([]);
  const [rtoOverride, setRtoOverride] = useState<WorkbookOverrideState>(
    emptyOverrideState(),
  );
  const [rtoError, setRtoError] = useState<string | null>(null);
  const [isProcessingRto, setIsProcessingRto] = useState(false);

  const [insuranceFiles, setInsuranceFiles] = useState<File[]>([]);
  const [insuranceOverride, setInsuranceOverride] = useState<WorkbookOverrideState>(
    emptyOverrideState(),
  );
  const [insuranceError, setInsuranceError] = useState<string | null>(null);
  const [isProcessingInsurance, setIsProcessingInsurance] = useState(false);

  const convertArtifact = artifacts.find((artifact) => artifact.stage === "convert") ?? null;
  const rtoArtifact = artifacts.find((artifact) => artifact.stage === "rto") ?? null;
  const insuranceArtifact = artifacts.find((artifact) => artifact.stage === "insurance") ?? null;

  const rtoBaseWorkbook = rtoOverride.file ?? currentWorkbook?.file ?? null;
  const insuranceBaseWorkbook = insuranceOverride.file ?? currentWorkbook?.file ?? null;

  const rtoEffectiveWorkbookName = rtoOverride.fileName ?? currentWorkbook?.fileName ?? null;
  const insuranceEffectiveWorkbookName =
    insuranceOverride.fileName ?? currentWorkbook?.fileName ?? null;

  const rtoEffectiveWorkbookSource = rtoOverride.file
    ? "Using workbook override"
    : currentWorkbook
      ? `Using latest workbook from ${STAGE_LABELS[currentWorkbook.sourceStage]}`
      : null;

  const insuranceEffectiveWorkbookSource = insuranceOverride.file
    ? "Using workbook override"
    : currentWorkbook
      ? `Using latest workbook from ${STAGE_LABELS[currentWorkbook.sourceStage]}`
      : null;

  useEffect(() => {
    if (artifacts.length === 0) {
      setSelectedArtifactId(null);
      setPreviewMode("worksheet");
      return;
    }

    if (
      selectedArtifactId
      && artifacts.some((artifact) => artifact.id === selectedArtifactId)
    ) {
      return;
    }

    const latestArtifact = [...artifacts].sort(
      (left, right) => right.completedOrder - left.completedOrder,
    )[0];
    setSelectedArtifactId(latestArtifact?.id ?? null);
    setPreviewMode(
      latestArtifact?.reviewRows?.length ? "review" : "worksheet",
    );
  }, [artifacts, selectedArtifactId]);

  function handleSettingsChange(
    key: keyof Settings,
    value: string | boolean,
  ) {
    setSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  async function validateWorkbookOverride(
    file: File | null,
    setter: (nextState: WorkbookOverrideState) => void,
  ) {
    if (!file) {
      setter(emptyOverrideState());
      return;
    }

    try {
      const preview = await readWorkbookPreview(file);
      setter({
        file,
        preview,
        error: null,
        fileName: file.name,
      });
    } catch (error) {
      setter({
        file: null,
        preview: null,
        error:
          error instanceof Error ? error.message : "Failed to read workbook.",
        fileName: file.name,
      });
    }
  }

  function clearRtoStageState() {
    setRtoFiles([]);
    setRtoOverride(emptyOverrideState());
    setRtoError(null);
  }

  function clearInsuranceStageState() {
    setInsuranceFiles([]);
    setInsuranceOverride(emptyOverrideState());
    setInsuranceError(null);
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

      const nextArtifacts = mergeArtifacts(artifacts, artifact, [
        "rto",
        "insurance",
      ]);

      setArtifacts(nextArtifacts);
      setCurrentWorkbook({
        file: workbook.file,
        preview: workbook.preview,
        downloadUrl: result.downloadUrl,
        fileName: workbook.fileName,
        sourceStage: "convert",
      });
      setSelectedArtifactId(artifact.id);
      setPreviewMode("worksheet");
      setActiveTab(STAGE_NEXT_TAB.convert);
      clearRtoStageState();
      clearInsuranceStageState();
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
    const baseWorkbook = isRto ? rtoBaseWorkbook : insuranceBaseWorkbook;
    const receiptFiles = isRto ? rtoFiles : insuranceFiles;
    const overrideError = isRto ? rtoOverride.error : insuranceOverride.error;
    const setError = isRto ? setRtoError : setInsuranceError;
    const setProcessing = isRto ? setIsProcessingRto : setIsProcessingInsurance;

    if (!baseWorkbook || receiptFiles.length === 0 || overrideError) {
      return;
    }

    const formData = new FormData();
    formData.append("workbook", baseWorkbook);
    if (isRto) {
      receiptFiles.forEach((file) => formData.append("rto_files[]", file));
    } else {
      receiptFiles.forEach((file) => formData.append("insurance_files[]", file));
    }
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
        displayLabel:
          stageId === "rto" ? "RTO updated workbook" : "Insurance updated workbook",
        workbookDownloadUrl: result.downloadUrl,
        workbookFile: workbook.file,
        workbookPreview: workbook.preview,
        workbookFileName: workbook.fileName,
        sourceWorkbookFileName: baseWorkbook.name,
        reviewCsvUrl: result.reviewCsvUrl,
        summary: result.summary,
        reviewRows: result.reviewRows,
        completedOrder,
      };

      const invalidatedStages: WorkflowStageId[] =
        stageId === "rto" ? ["insurance"] : [];
      const nextArtifacts = mergeArtifacts(artifacts, artifact, invalidatedStages);

      setArtifacts(nextArtifacts);
      setCurrentWorkbook({
        file: workbook.file,
        preview: workbook.preview,
        downloadUrl: result.downloadUrl,
        fileName: workbook.fileName,
        sourceStage: stageId,
      });
      setSelectedArtifactId(artifact.id);
      setPreviewMode(result.reviewRows.length > 0 ? "review" : "worksheet");
      setActiveTab(STAGE_NEXT_TAB[stageId]);

      if (isRto) {
        clearRtoStageState();
        clearInsuranceStageState();
      } else {
        clearInsuranceStageState();
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "Processing failed.");
    } finally {
      setProcessing(false);
    }
  }

  function buildConvertStatus(): StageStatus {
    if (isGeneratingWorkbook) {
      return { text: "Working", tone: "info" };
    }
    if (convertArtifact) {
      return { text: "Completed", tone: "completed" };
    }
    if (rawInvoiceFile) {
      return { text: "Ready", tone: "ready" };
    }
    return { text: "Not started", tone: "neutral" };
  }

  function buildUpdateStatus(stageId: UpdateStageId): StageStatus {
    const artifact = stageId === "rto" ? rtoArtifact : insuranceArtifact;
    const isProcessing = stageId === "rto" ? isProcessingRto : isProcessingInsurance;
    const overrideState = stageId === "rto" ? rtoOverride : insuranceOverride;
    const baseWorkbook = stageId === "rto" ? rtoBaseWorkbook : insuranceBaseWorkbook;

    if (isProcessing) {
      return { text: "Working", tone: "info" };
    }
    if (artifact) {
      return { text: "Completed", tone: "completed" };
    }
    if (overrideState.error || !baseWorkbook) {
      return { text: "Needs workbook", tone: "warning" };
    }
    return { text: "Ready", tone: "ready" };
  }

  function buildReviewStatus(): StageStatus {
    if (artifacts.length === 0) {
      return { text: "Awaiting output", tone: "neutral" };
    }
    return {
      text: `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}`,
      tone: "completed",
    };
  }

  const convertStatus = buildConvertStatus();
  const rtoStatus = buildUpdateStatus("rto");
  const insuranceStatus = buildUpdateStatus("insurance");
  const reviewStatus = buildReviewStatus();

  const rtoCanRun =
    Boolean(rtoBaseWorkbook)
    && rtoFiles.length > 0
    && !rtoOverride.error
    && !isProcessingRto;
  const insuranceCanRun =
    Boolean(insuranceBaseWorkbook)
    && insuranceFiles.length > 0
    && !insuranceOverride.error
    && !isProcessingInsurance;

  const rtoReadinessMessage = isProcessingRto
    ? "Processing workbook..."
    : rtoOverride.error
      ? "Clear or replace the invalid workbook override before running this stage."
      : !rtoBaseWorkbook
        ? "Generate stage 1 output first, or upload a workbook override to resume directly at RTO."
        : rtoFiles.length === 0
          ? "Upload at least one RTO receipt to continue."
          : "Ready to update the RTO column in the current workbook.";

  const insuranceReadinessMessage = isProcessingInsurance
    ? "Processing workbook..."
    : insuranceOverride.error
      ? "Clear or replace the invalid workbook override before running this stage."
      : !insuranceBaseWorkbook
        ? "Generate stage 1 output first, or upload a workbook override to resume directly at insurance."
        : insuranceFiles.length === 0
          ? "Upload at least one insurance file to continue."
          : "Ready to update the insurance column in the current workbook.";

  const tabs = [
    {
      id: "convert" as const,
      label: STAGE_TITLES.convert,
      status: convertStatus.text,
      tone: convertStatus.tone,
    },
    {
      id: "rto" as const,
      label: STAGE_TITLES.rto,
      status: rtoStatus.text,
      tone: rtoStatus.tone,
    },
    {
      id: "insurance" as const,
      label: STAGE_TITLES.insurance,
      status: insuranceStatus.text,
      tone: insuranceStatus.tone,
    },
    {
      id: "review" as const,
      label: STAGE_TITLES.review,
      status: reviewStatus.text,
      tone: reviewStatus.tone,
    },
  ];

  return (
    <main className="app-shell">
      <div className="workspace-frame">
        <header className="app-nav">
          <div className="compact-header">
            <p className="eyebrow">Guided workbook workflow</p>
            <h1>Invoice conversion and staged bill updates</h1>
            <p className="compact-copy">
              Generate the styled sales workbook first, then update RTO and
              insurance in separate guided stages. Every successful stage stays
              reviewable and downloadable in one artifact workspace.
            </p>
            <div className="status-chip-row">
              <span className="status-chip">{FIXED_HEADERS.customer}</span>
              <span className="status-chip">{FIXED_HEADERS.insurance}</span>
              <span className="status-chip">{FIXED_HEADERS.rto}</span>
            </div>
          </div>

          <StageTabs
            tabs={tabs}
            activeTab={activeTab}
            onSelect={setActiveTab}
          />
        </header>

        {activeTab === "review" ? (
          <ReviewWorkspace
            artifacts={artifacts}
            selectedArtifactId={selectedArtifactId}
            previewMode={previewMode}
            onSelectArtifact={(artifactId) => {
              const artifact = artifacts.find((entry) => entry.id === artifactId) ?? null;
              setSelectedArtifactId(artifactId);
              setPreviewMode(artifact?.reviewRows?.length ? "review" : "worksheet");
            }}
            onPreviewModeChange={setPreviewMode}
          />
        ) : (
          <section className="workspace-grid">
            <div className="control-panel">
              {activeTab === "convert" ? (
                <ConvertStagePanel
                  rawFile={rawInvoiceFile}
                  isProcessing={isGeneratingWorkbook}
                  error={convertError}
                  onRawFileChange={(file) => {
                    setRawInvoiceFile(file);
                    setConvertError(null);
                  }}
                  onRun={handleGenerateSalesRegister}
                />
              ) : null}

              {activeTab === "rto" ? (
                <UpdateStagePanel
                  stageId="rto"
                  title="Stage 2: Update RTO"
                  hint="Use the generated workbook from stage 1 or resume directly with a workbook override, then apply only the RTO receipts."
                  receiptFiles={rtoFiles}
                  overrideState={rtoOverride}
                  currentWorkbookName={currentWorkbook?.fileName ?? null}
                  currentWorkbookStageLabel={
                    currentWorkbook ? STAGE_LABELS[currentWorkbook.sourceStage] : null
                  }
                  effectiveWorkbookName={rtoEffectiveWorkbookName}
                  effectiveWorkbookSource={rtoEffectiveWorkbookSource}
                  isProcessing={isProcessingRto}
                  error={rtoError}
                  readinessMessage={rtoReadinessMessage}
                  canRun={rtoCanRun}
                  settings={settings}
                  onSettingsChange={handleSettingsChange}
                  onReceiptFilesChange={(files) => {
                    setRtoFiles(files);
                    setRtoError(null);
                  }}
                  onOverrideWorkbookChange={(file) => {
                    void validateWorkbookOverride(file, setRtoOverride);
                    setRtoError(null);
                  }}
                  onClearOverride={() => setRtoOverride(emptyOverrideState())}
                  onRun={() => {
                    void handleProcessStage("rto");
                  }}
                />
              ) : null}

              {activeTab === "insurance" ? (
                <UpdateStagePanel
                  stageId="insurance"
                  title="Stage 3: Update Insurance"
                  hint="Use the latest workbook output or resume directly with a workbook override, then apply only the insurance bills."
                  receiptFiles={insuranceFiles}
                  overrideState={insuranceOverride}
                  currentWorkbookName={currentWorkbook?.fileName ?? null}
                  currentWorkbookStageLabel={
                    currentWorkbook ? STAGE_LABELS[currentWorkbook.sourceStage] : null
                  }
                  effectiveWorkbookName={insuranceEffectiveWorkbookName}
                  effectiveWorkbookSource={insuranceEffectiveWorkbookSource}
                  isProcessing={isProcessingInsurance}
                  error={insuranceError}
                  readinessMessage={insuranceReadinessMessage}
                  canRun={insuranceCanRun}
                  settings={settings}
                  onSettingsChange={handleSettingsChange}
                  onReceiptFilesChange={(files) => {
                    setInsuranceFiles(files);
                    setInsuranceError(null);
                  }}
                  onOverrideWorkbookChange={(file) => {
                    void validateWorkbookOverride(file, setInsuranceOverride);
                    setInsuranceError(null);
                  }}
                  onClearOverride={() => setInsuranceOverride(emptyOverrideState())}
                  onRun={() => {
                    void handleProcessStage("insurance");
                  }}
                />
              ) : null}
            </div>

            <WorkflowSummaryPanel
              currentWorkbook={currentWorkbook}
              artifacts={artifacts}
              onOpenReview={() => setActiveTab("review")}
            />
          </section>
        )}
      </div>
    </main>
  );
}

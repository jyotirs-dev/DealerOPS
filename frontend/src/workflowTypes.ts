import type { WorkbookPreview } from "./lib/workbook";

export type WorkflowStageId = "convert" | "rto" | "insurance";
export type WorkflowTabId = WorkflowStageId | "review";
export type UpdateStageId = "rto" | "insurance";
export type PreviewMode = "worksheet" | "review";

export type StageState =
  | "waiting"
  | "ready"
  | "working"
  | "completed"
  | "attention";

export type Settings = {
  customerLabels: string;
  amountLabels: string;
  amountPosition: "same_line" | "next_line";
  nameThreshold: string;
  clearExisting: boolean;
};

export type ProcessSummary = {
  billsProcessed: number;
  billsUpdated: number;
  rowsUpdated: number;
  billsReview: number;
  parseFailures: number;
  noMatch: number;
  multiMatch: number;
  rowConflicts: number;
};

export type ReviewRow = {
  billType: string;
  billFile: string;
  extractedCustomer: string;
  extractedAmount: string;
  bestScore: string;
  candidateSalesRows: string;
  reason: string;
};

export type ProcessResponse = {
  jobId: string;
  sheetTitle: string;
  headerRow: string[];
  rows: Array<Array<string | number | boolean | null>>;
  summary: ProcessSummary;
  reviewRows: ReviewRow[];
  downloadUrl: string;
  reviewCsvUrl: string;
};

export type SalesRegisterResponse = {
  jobId: string;
  rowsWritten: number;
  monthYear: string;
  manualColumns: string[];
  downloadUrl: string;
};

export type WorkflowArtifact = {
  id: string;
  stage: WorkflowStageId;
  displayLabel: string;
  workbookDownloadUrl: string;
  workbookFile: File;
  workbookPreview: WorkbookPreview | null;
  workbookFileName: string;
  sourceWorkbookFileName: string;
  reviewCsvUrl?: string;
  summary?: ProcessSummary;
  reviewRows?: ReviewRow[];
  monthYear?: string;
  rowsWritten?: number;
  manualColumns?: string[];
  completedOrder: number;
};

export type WorkingFileOrigin = WorkflowStageId | "upload";

export type WorkingFile = {
  file: File;
  preview: WorkbookPreview | null;
  fileName: string;
  origin: WorkingFileOrigin;
  downloadUrl?: string;
};

export const WORKING_FILE_ORIGIN_LABELS: Record<WorkingFileOrigin, string> = {
  convert: "Carried forward from Stage 1",
  rto: "Carried forward from Stage 2",
  insurance: "Carried forward from Stage 3",
  upload: "Uploaded manually",
};

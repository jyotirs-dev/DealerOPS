import { useState } from "react";

import type { ReviewRow, WorkflowArtifact } from "../workflowTypes";
import { buildSalesRowOptions } from "../lib/gridModel";
import { CheckIcon, CloseIcon } from "./icons";

const REVIEW_REASON_COPY: Record<string, string> = {
  NO_MATCH: "No matching sales row cleared the configured threshold.",
  MULTIPLE_SALES_ROWS: "Multiple sales rows matched the extracted customer.",
  MULTIPLE_BILLS_FOR_ROW_TYPE:
    "Multiple bills claimed the same sales row for this bill type.",
  EXISTING_TARGET_VALUE:
    "An existing value was preserved because Clear existing was off.",
};

function describeReason(reason: string): string {
  return reason
    .split(";")
    .map((segment) => segment.trim())
    .filter(Boolean)
    .map((segment) => {
      if (segment in REVIEW_REASON_COPY) {
        return REVIEW_REASON_COPY[segment];
      }
      if (segment.startsWith("TEXT_EXTRACTION_ERROR:")) {
        return segment.replace(
          "TEXT_EXTRACTION_ERROR:",
          "Text extraction failed:",
        );
      }
      return segment;
    })
    .join("; ");
}

function extractKnownRow(candidateSalesRows: string): number | null {
  const match = candidateSalesRows.match(/row=(\d+)/);
  return match ? Number(match[1]) : null;
}

function extractNumeric(text: string): string {
  const match = text.match(/[\d.]+/);
  return match ? match[0] : "";
}

export function reviewRowKey(row: ReviewRow): string {
  return `${row.billType}-${row.billFile}-${row.reason}`;
}

type SalesRowOption = { rowNumber: number; customerName: string };

type FlaggedRowProps = {
  row: ReviewRow;
  salesRowOptions: SalesRowOption[];
  onApply: (rowNumber: number, value: number) => Promise<void>;
  onDismiss: () => void;
};

function FlaggedRow({
  row,
  salesRowOptions,
  onApply,
  onDismiss,
}: FlaggedRowProps) {
  const knownRow = extractKnownRow(row.candidateSalesRows);
  const [selectedRow, setSelectedRow] = useState(
    knownRow ? String(knownRow) : "",
  );
  const [value, setValue] = useState(extractNumeric(row.extractedAmount));
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const numericValue = Number(value);
  const canApply =
    selectedRow !== "" && value !== "" && !Number.isNaN(numericValue);

  async function handleApply() {
    if (!canApply || isApplying) {
      return;
    }
    setIsApplying(true);
    setError(null);
    try {
      await onApply(Number(selectedRow), numericValue);
    } catch (applyError) {
      setError(
        applyError instanceof Error
          ? applyError.message
          : "Failed to apply the edit.",
      );
    } finally {
      setIsApplying(false);
    }
  }

  return (
    <div className="attention-row">
      <div className="attention-row-info">
        <span className="attention-row-file">{row.billFile}</span>
        <span className="attention-row-meta">
          {row.billType === "insurance" ? "Insurance" : "RTO"} ·{" "}
          {row.extractedCustomer || "Customer not found"}
        </span>
        <span className="attention-row-reason">
          {describeReason(row.reason)}
        </span>
      </div>

      <div className="attention-row-fields">
        <label className="attention-field">
          <span>Sales row</span>
          <select
            value={selectedRow}
            onChange={(event) => setSelectedRow(event.target.value)}
          >
            <option value="">Select a sales row…</option>
            {salesRowOptions.map((option) => (
              <option key={option.rowNumber} value={option.rowNumber}>
                Row {option.rowNumber} — {option.customerName}
              </option>
            ))}
          </select>
        </label>

        <label className="attention-field">
          <span>Amount</span>
          <input
            type="number"
            inputMode="decimal"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="0"
          />
        </label>

        <button
          type="button"
          className="secondary-button"
          disabled={!canApply || isApplying}
          onClick={() => {
            void handleApply();
          }}
        >
          {isApplying ? "Applying…" : "Apply"}
        </button>

        <button
          type="button"
          className="dismiss-button"
          onClick={onDismiss}
          disabled={isApplying}
        >
          <CloseIcon size={11} />
          Delete
        </button>
      </div>

      {error ? (
        <p className="error-banner attention-row-error">{error}</p>
      ) : null}
    </div>
  );
}

type NeedsAttentionListProps = {
  artifact: WorkflowArtifact;
  onApply: (reviewRow: ReviewRow, rowNumber: number, value: number) => Promise<void>;
  onDismiss: (reviewRow: ReviewRow) => void;
  onUndoDismiss: () => void;
};

export function NeedsAttentionList({
  artifact,
  onApply,
  onDismiss,
  onUndoDismiss,
}: NeedsAttentionListProps) {
  const reviewRows = artifact.reviewRows ?? [];
  const dismissedCount = artifact.dismissedReviewRows?.length ?? 0;
  const salesRowOptions = buildSalesRowOptions(artifact.workbookPreview);

  return (
    <div className="attention-list">
      {reviewRows.length === 0 ? (
        <div className="attention-clear">
          <span className="attention-clear-icon">
            <CheckIcon size={15} />
          </span>
          <div>
            <strong>Nothing left to review</strong>
            <span>
              Every bill in this stage was matched, fixed, or deleted.
            </span>
          </div>
        </div>
      ) : (
        reviewRows.map((row) => (
          <FlaggedRow
            key={reviewRowKey(row)}
            row={row}
            salesRowOptions={salesRowOptions}
            onApply={(rowNumber, value) => onApply(row, rowNumber, value)}
            onDismiss={() => onDismiss(row)}
          />
        ))
      )}

      {dismissedCount > 0 ? (
        <div className="attention-dismissed-bar">
          <span>
            {dismissedCount} deleted
          </span>
          <button type="button" className="link-button" onClick={onUndoDismiss}>
            Undo
          </button>
        </div>
      ) : null}
    </div>
  );
}

import { useEffect } from "react";

import type { Settings } from "../workflowTypes";
import { CloseIcon } from "./icons";

export const DEFAULT_SETTINGS: Settings = {
  customerLabels: "Insured, Insured Name, Received From",
  amountLabels:
    "Received with Thanks Rs, Grand Total (in Rs), Grand Total, Final Amount, Amount Payable, Net Payable",
  amountPosition: "same_line",
  nameThreshold: "95",
  clearExisting: false,
};

type ExtractionSettingsDrawerProps = {
  isOpen: boolean;
  settings: Settings;
  onSettingsChange: (key: keyof Settings, value: string | boolean) => void;
  onReset: () => void;
  onClose: () => void;
};

export function ExtractionSettingsDrawer({
  isOpen,
  settings,
  onSettingsChange,
  onReset,
  onClose,
}: ExtractionSettingsDrawerProps) {
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="drawer-layer">
      <button
        type="button"
        className="drawer-backdrop"
        aria-label="Close extraction settings"
        onClick={onClose}
      />
      <div
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="extraction-settings-title"
      >
        <header className="drawer-header">
          <div>
            <h2 id="extraction-settings-title">Extraction settings</h2>
            <p className="process-note">
              Shared by both the RTO and Insurance stages, so you only tune
              matching once per workbook.
            </p>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close settings"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </header>

        <div className="drawer-body">
          <div className="field-block">
            <label htmlFor="customer-labels">Customer labels</label>
            <input
              id="customer-labels"
              type="text"
              value={settings.customerLabels}
              onChange={(event) =>
                onSettingsChange("customerLabels", event.target.value)
              }
            />
            <span className="field-help">
              Text that appears before a customer name on a bill.
            </span>
          </div>

          <div className="field-block">
            <label htmlFor="amount-labels">Amount labels</label>
            <input
              id="amount-labels"
              type="text"
              value={settings.amountLabels}
              onChange={(event) =>
                onSettingsChange("amountLabels", event.target.value)
              }
            />
            <span className="field-help">
              Text that appears near the payable amount.
            </span>
          </div>

          <div className="field-block">
            <span className="field-block-label">Amount position</span>
            <div className="segmented" role="group" aria-label="Amount position">
              <button
                type="button"
                className={
                  settings.amountPosition === "same_line"
                    ? "segment active"
                    : "segment"
                }
                aria-pressed={settings.amountPosition === "same_line"}
                onClick={() => onSettingsChange("amountPosition", "same_line")}
              >
                Same line
              </button>
              <button
                type="button"
                className={
                  settings.amountPosition === "next_line"
                    ? "segment active"
                    : "segment"
                }
                aria-pressed={settings.amountPosition === "next_line"}
                onClick={() => onSettingsChange("amountPosition", "next_line")}
              >
                Next line
              </button>
            </div>
            <span className="field-help">
              Is the amount on the same line as its label, or the line after it?
            </span>
          </div>

          <div className="field-block">
            <div className="field-inline-header">
              <label htmlFor="name-threshold">Name match threshold</label>
              <strong className="field-value">{settings.nameThreshold}</strong>
            </div>
            <input
              id="name-threshold"
              type="range"
              min="0"
              max="100"
              step="0.1"
              value={settings.nameThreshold}
              onChange={(event) =>
                onSettingsChange("nameThreshold", event.target.value)
              }
            />
            <span className="field-help">
              How similar an extracted name must be to a sales row before it
              matches automatically.
            </span>
          </div>

          <label className="toggle-field">
            <input
              type="checkbox"
              checked={settings.clearExisting}
              onChange={(event) =>
                onSettingsChange("clearExisting", event.target.checked)
              }
            />
            <span>
              <strong>Clear existing values first</strong>
              <span className="field-help">
                Off by default — existing Insurance / RTO cells are preserved and
                flagged instead of overwritten.
              </span>
            </span>
          </label>
        </div>

        <footer className="drawer-footer">
          <button type="button" className="secondary-button" onClick={onReset}>
            Reset to defaults
          </button>
          <button type="button" className="primary-button" onClick={onClose}>
            Done
          </button>
        </footer>
      </div>
    </div>
  );
}

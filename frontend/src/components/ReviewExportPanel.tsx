import { AgGridReact } from "ag-grid-react";

import type { WorkflowArtifact } from "../workflowTypes";
import { buildGridModel } from "../lib/gridModel";
import type { GridRow } from "../lib/gridModel";
import { DownloadIcon } from "./icons";

type ReviewExportPanelProps = {
  artifact: WorkflowArtifact;
};

export function ReviewExportPanel({ artifact }: ReviewExportPanelProps) {
  const { columnDefs, rowData } = buildGridModel(artifact.workbookPreview);

  const summaryLine = artifact.summary
    ? `${artifact.summary.billsUpdated} of ${artifact.summary.billsProcessed} bills updated`
    : artifact.rowsWritten !== undefined
      ? `${artifact.rowsWritten} rows written`
      : null;

  return (
    <section className="result-panel export-panel">
      <header className="result-panel-header">
        <div className="result-panel-heading">
          <span className="result-dot" />
          <div>
            <h2>{artifact.displayLabel}</h2>
            {summaryLine ? (
              <p className="export-summary-line">{summaryLine}</p>
            ) : null}
          </div>
        </div>
        <a className="primary-button" href={artifact.workbookDownloadUrl}>
          <DownloadIcon />
          Download workbook
        </a>
      </header>

      <div className="grid-shell" aria-label="workbook preview">
        {artifact.workbookPreview ? (
          <div className="ag-theme-quartz grid-theme">
            <AgGridReact<GridRow>
              theme="legacy"
              rowData={rowData}
              columnDefs={columnDefs}
              animateRows
              pagination
              paginationPageSize={20}
            />
          </div>
        ) : (
          <div className="empty-grid">
            This workbook could not be previewed in the browser. Download it to
            inspect the contents.
          </div>
        )}
      </div>
    </section>
  );
}

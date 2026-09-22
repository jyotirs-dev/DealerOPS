import type { ColDef } from "ag-grid-community";

import type { WorkflowArtifact } from "../workflowTypes";

export type GridRow = Record<string, string | number | boolean | null>;

export function buildGridModel(preview: WorkflowArtifact["workbookPreview"]): {
  columnDefs: ColDef<GridRow>[];
  rowData: GridRow[];
} {
  if (!preview) {
    return { columnDefs: [], rowData: [] };
  }

  const columnDefs: ColDef<GridRow>[] = [
    {
      headerName: "#",
      field: "__rowNumber",
      width: 90,
      pinned: "left",
      sortable: false,
      filter: false,
      suppressMovable: true,
      cellClass: "row-number-cell",
    },
    ...preview.headerRow.map((header, index) => ({
      field: `col_${index}`,
      headerName: header || `Column ${index + 1}`,
      sortable: true,
      filter: true,
      resizable: true,
      flex: 1,
      minWidth: 180,
      tooltipField: `col_${index}`,
    })),
  ];

  const rowData = preview.rows.map((row, rowIndex) => {
    const record: GridRow = { __rowNumber: rowIndex + 2 };
    preview.headerRow.forEach((_, index) => {
      record[`col_${index}`] = row[index] ?? "";
    });
    return record;
  });

  return { columnDefs, rowData };
}

export function findCustomerColumnIndex(headerRow: string[]): number {
  const index = headerRow.findIndex(
    (header) => header.trim().toLowerCase() === "contact name",
  );
  return index === -1 ? 0 : index;
}

export function buildSalesRowOptions(
  preview: WorkflowArtifact["workbookPreview"],
): Array<{ rowNumber: number; customerName: string }> {
  if (!preview) {
    return [];
  }
  const customerColumn = findCustomerColumnIndex(preview.headerRow);
  return preview.rows
    .map((row, index) => ({
      rowNumber: index + 2,
      customerName: String(row[customerColumn] ?? "").trim(),
    }))
    .filter((option) => option.customerName.length > 0);
}

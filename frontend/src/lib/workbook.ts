import { HyperFormula } from "hyperformula";
import type { RawCellContent, Sheets } from "hyperformula";
import * as XLSX from "xlsx";

export type WorkbookPreview = {
  fileName: string;
  sheetTitle: string;
  headerRow: string[];
  rows: Array<Array<string | number | boolean | null>>;
};

export const FIXED_HEADERS = {
  customer: "Contact Name",
  insurance: "Insurance",
  rto: "(RTO+ Agent fee 500)",
} as const;

function normalizeHeader(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function trimTrailingEmpty(row: unknown[]): unknown[] {
  const trimmed = [...row];
  while (
    trimmed.length > 0 &&
    (trimmed[trimmed.length - 1] === undefined ||
      trimmed[trimmed.length - 1] === null ||
      trimmed[trimmed.length - 1] === "")
  ) {
    trimmed.pop();
  }
  return trimmed;
}

function worksheetToMatrix(worksheet: XLSX.WorkSheet): unknown[][] {
  const ref = worksheet["!ref"];
  if (!ref) {
    return [];
  }

  const range = XLSX.utils.decode_range(ref);
  const matrix: unknown[][] = [];

  for (let rowIndex = range.s.r; rowIndex <= range.e.r; rowIndex += 1) {
    const row: unknown[] = [];
    for (let colIndex = range.s.c; colIndex <= range.e.c; colIndex += 1) {
      const address = XLSX.utils.encode_cell({ r: rowIndex, c: colIndex });
      row.push(worksheet[address]);
    }
    matrix.push(row);
  }

  return matrix;
}

function buildFormulaSource(workbook: XLSX.WorkBook): Sheets {
  const sheets: Sheets = {};

  for (const sheetTitle of workbook.SheetNames) {
    const worksheet = workbook.Sheets[sheetTitle];
    const rows = worksheetToMatrix(worksheet).map((row) =>
      row.map((cell): RawCellContent => {
        const typedCell = cell as XLSX.CellObject | undefined;
        if (!typedCell) {
          return null;
        }
        if (typedCell.f) {
          return `=${typedCell.f}`;
        }
        if (typedCell.t === "e") {
          return null;
        }
        if (typedCell.v === undefined || typedCell.v === null) {
          return null;
        }
        if (typedCell.t === "b") {
          return Boolean(typedCell.v);
        }
        if (typedCell.t === "n") {
          return Number(typedCell.v);
        }
        return String(typedCell.v);
      }),
    );
    sheets[sheetTitle] = rows;
  }

  return sheets;
}

function evaluateWorkbookFormulas(
  workbook: XLSX.WorkBook,
): Map<string, unknown[][]> {
  const results = new Map<string, unknown[][]>();

  try {
    const hf = HyperFormula.buildFromSheets(buildFormulaSource(workbook), {
      licenseKey: "gpl-v3",
    });

    for (const sheetTitle of workbook.SheetNames) {
      const sheetId = hf.getSheetId(sheetTitle);
      if (sheetId === undefined) {
        continue;
      }
      results.set(sheetTitle, hf.getSheetValues(sheetId) as unknown[][]);
    }
  } catch {
    return results;
  }

  return results;
}

function normalizeDisplayValue(value: unknown): string | number | boolean {
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  return String(value);
}

function matrixToDisplayRows(
  worksheet: XLSX.WorkSheet,
  evaluatedRows: unknown[][] | undefined,
): unknown[][] {
  return worksheetToMatrix(worksheet).map((row, rowIndex) =>
    row.map((cell, colIndex) => {
      const typedCell = cell as XLSX.CellObject | undefined;
      const evaluatedValue = evaluatedRows?.[rowIndex]?.[colIndex];

      if (typedCell?.f) {
        if (
          evaluatedValue !== undefined &&
          evaluatedValue !== null &&
          `${evaluatedValue}` !== "#LIC!"
        ) {
          return normalizeDisplayValue(evaluatedValue);
        }
        if (typedCell.w !== undefined && typedCell.w !== "") {
          return normalizeDisplayValue(typedCell.w);
        }
        if (typedCell.v !== undefined && typedCell.v !== null) {
          return normalizeDisplayValue(typedCell.v);
        }
        return `=${typedCell.f}`;
      }

      if (!typedCell) {
        return "";
      }
      if (typedCell.w !== undefined && typedCell.w !== "") {
        return normalizeDisplayValue(typedCell.w);
      }
      if (typedCell.v !== undefined && typedCell.v !== null) {
        return normalizeDisplayValue(typedCell.v);
      }
      return "";
    }),
  );
}

export async function readWorkbookPreview(file: File): Promise<WorkbookPreview> {
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, {
    type: "array",
    cellFormula: true,
    cellNF: true,
    cellText: true,
    sheetStubs: true,
  });
  const evaluatedSheets = evaluateWorkbookFormulas(workbook);

  const requiredHeaders = new Set(
    Object.values(FIXED_HEADERS).map(normalizeHeader),
  );

  for (const sheetTitle of workbook.SheetNames) {
    const worksheet = workbook.Sheets[sheetTitle];
    const matrix = matrixToDisplayRows(
      worksheet,
      evaluatedSheets.get(sheetTitle),
    );
    if (matrix.length === 0) {
      continue;
    }

    const headerRow = trimTrailingEmpty(matrix[0] ?? []).map((value) =>
      String(value ?? "").trim(),
    );
    const availableHeaders = new Set(
      headerRow.map(normalizeHeader).filter(Boolean),
    );

    if (![...requiredHeaders].every((header) => availableHeaders.has(header))) {
      continue;
    }

    const rows = matrix.slice(1).map((row) =>
      headerRow.map((_, index) => {
        const value = row[index];
        if (value === undefined || value === null || value === "") {
          return "";
        }
        return value as string | number | boolean;
      }),
    );

    return {
      fileName: file.name,
      sheetTitle,
      headerRow,
      rows,
    };
  }

  throw new Error(
    "Workbook must contain a worksheet with headers: Contact Name, Insurance, (RTO+ Agent fee 500).",
  );
}

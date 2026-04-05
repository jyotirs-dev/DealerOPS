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

export async function readWorkbookPreview(file: File): Promise<WorkbookPreview> {
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, {
    type: "array",
    cellDates: true,
  });

  const requiredHeaders = new Set(
    Object.values(FIXED_HEADERS).map(normalizeHeader),
  );

  for (const sheetTitle of workbook.SheetNames) {
    const worksheet = workbook.Sheets[sheetTitle];
    const matrix = XLSX.utils.sheet_to_json<unknown[]>(worksheet, {
      header: 1,
      raw: false,
      defval: "",
      blankrows: false,
    });
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

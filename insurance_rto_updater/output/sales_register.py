"""
sales_register.py – Vehicle Sales Register generator
=====================================================
Transforms a raw OEM / DMS invoice export (.xlsx) into a formatted
Vehicle Sales Register workbook with:

  • Auto-filled columns from raw data  (A, B, C, D, E, F, G, H, J, O, Z)
  • Formula columns                     (K, P, Q, S, T, U, W, X)
  • Blank columns for manual entry      (I, L, M, N, R, V, Y, AA, AB)

The output is a standalone .xlsx file ready for the dealership to open,
fill in the manual columns, and let the formulas compute the rest.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from insurance_rto_updater.models import SalesRegisterResult


# ── Constants ─────────────────────────────────────────────────────────────────

DEALER_NAME = "SHREE DURGA DARSHAN AUTOMOBILES"

HEADERS = [
    "Invoice Date",
    "Invoice No.",
    "Contact Name",
    "Contact \nMobile No.",
    "Contact \nAddress",
    "Model Name",
    "Color",
    "VIN",
    "Discount \nPre",
    "Total\n Invoice",
    "Ex \nShowroom",
    "(RTO+\n Agent fee 500)",
    "Insurance",
    "Accesories",
    "Discount",
    "Expected \nOn Road Price",
    "Actual On\nRoad Price",
    "Down \nPayment",
    "Filed DP\n(to Bank)",
    "Our \nComission",
    "Agent \nComission",
    "FINANCE \nDISBURSEMENT",
    "Expected \nGAP",
    "Actual \nGap",
    "Outstanding",
    "Financer Name (HP With)",
    "Remarks",
    "Status",
]

MANUAL_COLUMNS = [
    "I  – Discount Pre",
    "L  – RTO + Agent Fee",
    "M  – Insurance premium",
    "N  – Accessories",
    "R  – Down Payment",
    "V  – Finance Disbursement",
    "Y  – Outstanding",
    "AA – Remarks",
    "AB – Status",
]

FONT_SIZE = 9
GST_RATE = 0.18
EX_SHOWROOM_DEDUCTION = 1099.72
CHAR_WIDTH = 1.1


# ── Styling helpers ───────────────────────────────────────────────────────────

def _thin_border() -> Border:
    side = Side(style="thin")
    return Border(left=side, right=side, top=side, bottom=side)


def _header_style(cell) -> None:  # type: ignore[no-untyped-def]
    cell.font = Font(bold=True, size=FONT_SIZE)
    cell.alignment = Alignment(
        horizontal="center", vertical="center", wrap_text=True,
    )


def _data_style(cell) -> None:  # type: ignore[no-untyped-def]
    cell.font = Font(size=FONT_SIZE)
    cell.alignment = Alignment(horizontal="center", vertical="center")


# ── Raw-column extractor ─────────────────────────────────────────────────────

def _safe_value(row: pd.Series, col_name: str):  # type: ignore[type-arg]
    """Return the column value or None when missing / NaN."""
    val = row.get(col_name)
    if val is None or pd.isna(val):
        return None
    return val


def _coerce_mobile_number(value):  # type: ignore[no-untyped-def]
    """Best-effort int conversion; unparseable/missing values become None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_invoiced_rows(raw_path: Path) -> pd.DataFrame:
    """Read the raw OEM/DMS export and keep only rows marked Invoiced."""
    raw_df = pd.read_excel(raw_path, sheet_name=0)
    raw_df.columns = [c.strip() for c in raw_df.columns]
    if "Invoice Status" not in raw_df.columns:
        raise ValueError(
            "Raw invoice export is missing the required 'Invoice Status' column."
        )
    return raw_df[raw_df["Invoice Status"] == "Invoiced"].reset_index(drop=True)


def _detect_month_year(invoiced_rows: pd.DataFrame) -> str:
    """Derive a "MonYYYY" label from the first row's invoice date, if any."""
    invoice_dates = invoiced_rows["Invoice Date"].dropna()
    if invoice_dates.empty:
        return ""
    first_date = pd.to_datetime(invoice_dates.iloc[0], errors="coerce")
    if pd.notna(first_date):
        return first_date.strftime("%b%Y")
    return ""


def _write_header_row(worksheet) -> None:  # type: ignore[no-untyped-def]
    worksheet.row_dimensions[1].height = 30.0
    for column_index, header in enumerate(HEADERS, start=1):
        cell = worksheet.cell(row=1, column=column_index, value=header)
        _header_style(cell)
        cell.border = _thin_border()


def _write_data_row(worksheet, row_data: pd.Series, excel_row: int) -> None:  # type: ignore[no-untyped-def, type-arg]
    """
    Write one invoice's values/formulas into `excel_row`.

    Column letters below match the fixed `HEADERS` layout and the manual-entry
    columns documented in `MANUAL_COLUMNS`; formulas reference sibling cells by
    letter because the output is a live workbook the dealership edits by hand.
    """
    # A: Invoice Date
    worksheet[f"A{excel_row}"] = _safe_value(row_data, "Invoice Date")
    worksheet[f"A{excel_row}"].number_format = "d mmmm yyyy"

    # B: Invoice Number
    worksheet[f"B{excel_row}"] = _safe_value(row_data, "Invoice Number")

    # C: Contact Name
    worksheet[f"C{excel_row}"] = _safe_value(row_data, "Contact Name")

    # D: Contact Mobile Number
    mobile = _safe_value(row_data, "Contact Mobile Number")
    worksheet[f"D{excel_row}"] = _coerce_mobile_number(mobile)

    # E: Contact Address
    worksheet[f"E{excel_row}"] = _safe_value(row_data, "Contact Address")

    # F: Model Name
    worksheet[f"F{excel_row}"] = _safe_value(row_data, "Model Name")

    # G: Color
    worksheet[f"G{excel_row}"] = _safe_value(row_data, "Color")

    # H: VIN
    worksheet[f"H{excel_row}"] = _safe_value(row_data, "VIN")

    # I: Discount Pre — manual entry (blank)

    # J: Total Invoice Amount
    worksheet[f"J{excel_row}"] = _safe_value(row_data, "Total Invoice Amount")
    worksheet[f"J{excel_row}"].number_format = "0.00"

    # K: Ex Showroom = J - 1099.72
    worksheet[f"K{excel_row}"] = f"=J{excel_row}-{EX_SHOWROOM_DEDUCTION}"
    worksheet[f"K{excel_row}"].number_format = "0.00"

    # L: RTO + Agent fee — manual entry (blank)
    # M: Insurance — manual entry (blank)
    # N: Accessories — manual entry (blank)

    # O: Discount = Pre Vat Discount + 18% GST (0 if no discount)
    pre_vat = _safe_value(row_data, "Pre Vat Discount")
    if pre_vat and float(pre_vat) > 0:
        worksheet[f"O{excel_row}"] = round(float(pre_vat) * (1 + GST_RATE), 2)
    else:
        worksheet[f"O{excel_row}"] = None

    # P: Expected On Road Price = K+L+M+N-O+200
    worksheet[f"P{excel_row}"] = (
        f"=K{excel_row}+L{excel_row}+M{excel_row}+N{excel_row}-O{excel_row}+200"
    )
    worksheet[f"P{excel_row}"].number_format = "0.00"

    # Q: Actual On Road Price = J+L+M-O
    worksheet[f"Q{excel_row}"] = (
        f"=J{excel_row}+L{excel_row}+M{excel_row}-O{excel_row}"
    )
    worksheet[f"Q{excel_row}"].number_format = "0.00"

    # R: Down Payment — manual entry (blank)

    # S: Filed DP to Bank = IF(ISTEXT(Z), R-3500, R)
    worksheet[f"S{excel_row}"] = (
        f"=IF(ISTEXT(Z{excel_row}),(R{excel_row}-3500),R{excel_row})"
    )
    worksheet[f"S{excel_row}"].number_format = "0.00"

    # T: Our Commission = R-S-U
    worksheet[f"T{excel_row}"] = f"=R{excel_row}-S{excel_row}-U{excel_row}"
    worksheet[f"T{excel_row}"].number_format = "0.00"

    # U: Agent Commission = IF(ISTEXT(Z), 1000, 0)
    worksheet[f"U{excel_row}"] = f"=IF(ISTEXT(Z{excel_row}),1000,0)"
    worksheet[f"U{excel_row}"].number_format = "0.00"

    # V: Finance Disbursement — manual entry (blank)

    # W: Expected GAP = P-S-V
    worksheet[f"W{excel_row}"] = f"=P{excel_row}-S{excel_row}-V{excel_row}"
    worksheet[f"W{excel_row}"].number_format = "0.00"

    # X: Actual Gap = Q-S-V
    worksheet[f"X{excel_row}"] = f"=Q{excel_row}-S{excel_row}-V{excel_row}"
    worksheet[f"X{excel_row}"].number_format = "0.00"

    # Y: Outstanding — manual entry (blank)

    # Z: Financer Name
    worksheet[f"Z{excel_row}"] = _safe_value(row_data, "Financer Name")

    # AA: Remarks — manual entry (blank)
    # AB: Status — manual entry (blank)


def _apply_row_styling(worksheet, excel_row: int) -> None:  # type: ignore[no-untyped-def]
    for column_index in range(1, len(HEADERS) + 1):
        cell = worksheet.cell(row=excel_row, column=column_index)
        _data_style(cell)
        cell.border = _thin_border()


def _autofit_column_widths(worksheet) -> None:  # type: ignore[no-untyped-def]
    """
    Size each column to its longest displayed value.

    Formula cells are skipped because their displayed width depends on the
    computed result, not the formula text, so measuring the formula string
    would produce misleadingly wide columns.
    """
    for column_index in range(1, len(HEADERS) + 1):
        column_letter = get_column_letter(column_index)
        max_length = 0
        for row in worksheet.iter_rows(min_col=column_index, max_col=column_index):
            for cell in row:
                if cell.value is None:
                    continue
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    continue
                lines = str(cell.value).split("\n")
                cell_length = max(len(line) for line in lines)
                if cell_length > max_length:
                    max_length = cell_length
        worksheet.column_dimensions[column_letter].width = max(
            max_length * CHAR_WIDTH + 2, 8,
        )


# ── Public API ────────────────────────────────────────────────────────────────

def generate_sales_register(
    raw_path: Path,
    output_path: Path,
) -> SalesRegisterResult:
    """
    Read a raw invoice export and produce a styled Vehicle Sales Register.

    Parameters
    ----------
    raw_path:
        Path to the raw .xlsx file exported from the OEM / DMS system.
    output_path:
        Destination for the generated workbook.

    Returns
    -------
    SalesRegisterResult with the output path, row count, and month/year.
    """
    invoiced_rows = _load_invoiced_rows(raw_path)
    month_year = _detect_month_year(invoiced_rows)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Vehicle Sales Register"

    _write_header_row(worksheet)

    for row_position, row_data in invoiced_rows.iterrows():
        excel_row = int(row_position) + 2  # type: ignore[arg-type]  # +2: header row + 1-based indexing
        _write_data_row(worksheet, row_data, excel_row)
        _apply_row_styling(worksheet, excel_row)

    _autofit_column_widths(worksheet)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)

    return SalesRegisterResult(
        output_path=output_path,
        rows_written=len(invoiced_rows),
        month_year=month_year,
        manual_columns=list(MANUAL_COLUMNS),
    )

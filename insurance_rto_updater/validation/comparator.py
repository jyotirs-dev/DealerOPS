"""
comparator.py – Compare extracted data with sheet data
=======================================================
Deterministic, pure functions that highlight mismatches between
bill extractions and the Google Sheet's current state.

These helpers are used primarily by the orchestration layer to build
a ``SheetWritePlan`` and by future modules that might surface
pre-/post-update comparisons to the user.

All functions are **side-effect-free** and trivially testable.
"""
from __future__ import annotations

from insurance_rto_updater.domain.normalization import (
    normalize_customer_name,
    normalize_text,
)
from insurance_rto_updater.models import (
    Assignment,
    CellValueUpdate,
    SalesRow,
    SheetWritePlan,
)


# ---------------------------------------------------------------------------
# Sheet structure helpers
# ---------------------------------------------------------------------------

def find_header_indices(
    header_row: list[str],
    customer_header: str,
    insurance_header: str,
    rto_header: str,
) -> tuple[int, int, int]:
    """
    Map user-supplied header names to 1-based column indices.

    Comparison is case-insensitive and whitespace-normalized so that
    "  Customer Name " matches "customer name".

    Returns
    -------
    (customer_col, insurance_col, rto_col) – all 1-based.

    Raises
    ------
    ValueError:
        If any header is not found in the sheet.
    """
    header_map: dict[str, int] = {}
    for col_idx, cell in enumerate(header_row, start=1):
        value = str(cell).strip() if cell is not None else ""
        if value:
            header_map[normalize_text(value)] = col_idx

    def lookup(header_name: str) -> int:
        key = normalize_text(header_name)
        if key not in header_map:
            raise ValueError(f"Header not found in sheet: {header_name}")
        return header_map[key]

    return lookup(customer_header), lookup(insurance_header), lookup(rto_header)


def build_sales_rows(
    data_rows: list[list[str]],
    customer_col: int,
) -> tuple[list[SalesRow], int]:
    """
    Convert raw sheet data rows into ``SalesRow`` records.

    Parameters
    ----------
    data_rows:
        The rows below the header (0-indexed list of lists).
    customer_col:
        1-based column index of the customer name column.

    Returns
    -------
    (sales_rows, max_row):
        - ``sales_rows``: list of ``SalesRow`` instances (only rows with
          non-empty customer names).
        - ``max_row``: the highest 1-based row index in the sheet (used
          for clearing columns before writing).
    """
    sales_rows: list[SalesRow] = []
    for row_idx, row in enumerate(data_rows, start=2):
        customer_value = row[customer_col - 1] if customer_col - 1 < len(row) else ""
        customer_raw = str(customer_value).strip()
        if not customer_raw:
            continue
        sales_rows.append(
            SalesRow(
                row_index=row_idx,
                customer_raw=customer_raw,
                customer_norm=normalize_customer_name(customer_raw),
            )
        )
    max_row = len(data_rows) + 1
    return sales_rows, max_row


# ---------------------------------------------------------------------------
# Write-plan construction
# ---------------------------------------------------------------------------

def build_sheet_write_plan(
    accepted_assignments: list[Assignment],
    insurance_col: int,
    rto_col: int,
    max_row: int,
    clear_existing: bool,
) -> SheetWritePlan:
    """
    Build a batch of cell updates (and optional column clears) from
    the list of accepted bill → row assignments.

    Each assignment maps to exactly one ``CellValueUpdate``:
      - Insurance bills write to ``insurance_col``.
      - RTO bills write to ``rto_col``.

    If ``clear_existing`` is ``True``, both insurance and RTO columns
    are blanked from row 2 to ``max_row`` *before* writing — this
    ensures that stale values from previous runs are removed.
    """
    value_updates = [
        CellValueUpdate(
            row_index=a.row_index,
            col_index=insurance_col if a.bill_type == "insurance" else rto_col,
            value=float(a.amount),
        )
        for a in accepted_assignments
    ]

    clear_columns = [insurance_col, rto_col] if clear_existing else []
    clear_from_row = 2
    clear_to_row = max(max_row, 2)

    return SheetWritePlan(
        clear_from_row=clear_from_row,
        clear_to_row=clear_to_row,
        clear_columns=clear_columns,
        value_updates=value_updates,
    )

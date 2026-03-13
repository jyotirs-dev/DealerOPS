"""
models.py – Shared data containers
===================================
All data-classes used across the pipeline live here so that every module
imports from a single source of truth.  These are *plain data holders* with
no behaviour — keeping them pure and trivially serializable.

Design note:
  Every field is typed and documented.  Frozen dataclasses would be ideal for
  immutability but are intentionally avoided because some consumers (CSV writer,
  Jinja templates) need dict-like attribute access that frozen classes make
  awkward.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ProcessingConfig:
    """
    User-supplied parameters that control the entire processing pipeline.

    Attributes
    ----------
    sheet_name:
        Optional worksheet tab name.  ``None`` means "use the first sheet".
    customer_header:
        Column header in the Google Sheet that contains customer names.
    insurance_header:
        Column header for the insurance-amount column to overwrite.
    rto_header:
        Column header for the RTO-amount column to overwrite.
    customer_labels:
        Possible text labels that appear on a bill *before* the customer name.
        Used by the text parser to locate the name.
    amount_labels:
        Possible text labels that appear near the final payable amount.
    amount_position:
        Strategy for extracting the amount relative to its label.
        ``"same_line"`` → amount is on the same line as the label.
        ``"next_line"`` → amount is on the line immediately after the label.
    name_threshold:
        Fuzzy-match similarity cutoff (0–100).  Pairs scoring below this
        value are rejected unless the safe-fallback heuristic applies.
    clear_existing:
        If ``True``, the pipeline blanks the insurance & RTO columns
        before writing new values (prevents stale data leaking through).
    """

    sheet_name: str | None
    customer_header: str
    insurance_header: str
    rto_header: str
    customer_labels: list[str]
    amount_labels: list[str]
    amount_position: str          # "same_line" | "next_line"
    name_threshold: float         # 0 – 100
    clear_existing: bool


# ---------------------------------------------------------------------------
# Intermediate pipeline records
# ---------------------------------------------------------------------------

@dataclass
class SalesRow:
    """
    One row from the Google Sheet's sales data.

    ``row_index`` is 1-based (matching the sheet's visual row numbers);
    row 1 is the header, so data starts at row 2.
    """

    row_index: int        # 1-based sheet row
    customer_raw: str     # original, untouched customer text
    customer_norm: str    # lowercased, whitespace-collapsed for comparison


@dataclass
class BillParseResult:
    """
    Output of the extraction layer for a single bill file.

    If extraction fails, ``error`` is set and the other fields may be empty.
    """

    bill_type: str                        # "insurance" | "rto"
    file_name: str                        # original filename
    raw_text: str = ""                    # full OCR / PDF text
    customer_name: str | None = None      # parsed customer name (or None)
    amount: Decimal | None = None         # parsed final amount (or None)
    customer_error: str | None = None     # reason customer extraction failed
    amount_error: str | None = None       # reason amount extraction failed
    extraction_error: str | None = None   # reason file-level extraction failed


@dataclass
class Assignment:
    """
    A successful bill → sheet-row mapping.

    Created when exactly one sales row matches a bill's customer name
    above the similarity threshold (or via the safe-fallback heuristic).
    """

    bill_type: str          # "insurance" | "rto"
    bill_file: str          # filename
    row_index: int          # 1-based sheet row that was matched
    amount: Decimal         # extracted bill amount
    matched_customer: str   # raw customer name from the matched sheet row
    score: float            # similarity score that justified the match


# ---------------------------------------------------------------------------
# Review / conflict reporting
# ---------------------------------------------------------------------------

@dataclass
class ReviewRow:
    """
    One entry in the review-conflicts CSV.

    Built for any bill that cannot be confidently matched:
      - Parse failures (OCR or field extraction)
      - No match above threshold
      - Multiple equally-good matches
      - Multiple bills claiming the same sheet row + bill type
    """

    bill_type: str
    bill_file: str
    extracted_customer: str
    extracted_amount: str
    best_score: str
    candidate_sales_rows: str
    reason: str


# ---------------------------------------------------------------------------
# Final pipeline output
# ---------------------------------------------------------------------------

@dataclass
class ProcessingResult:
    """
    Summary returned to the Flask app after the pipeline finishes.

    Contains both aggregate counters and the path to the review CSV so the
    web UI can render results and offer a download link.
    """

    review_csv_path: Path
    bills_processed: int
    bills_updated: int
    rows_updated: int
    bills_review: int
    parse_failures: int
    no_match: int
    multi_match: int
    row_conflicts: int
    sheet_reference: str
    sheet_title: str


# ---------------------------------------------------------------------------
# Google Sheets data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class SheetData:
    """
    The raw content loaded from a single Google Sheets worksheet.
    """

    spreadsheet_id: str
    spreadsheet_url: str
    sheet_title: str
    header_row: list[str]
    data_rows: list[list[str]]


@dataclass
class CellValueUpdate:
    """
    A single cell write instruction: "put *value* at (row, col)".
    """

    row_index: int   # 1-based sheet row
    col_index: int   # 1-based sheet column
    value: float


@dataclass
class SheetWritePlan:
    """
    A batch of cell updates plus optional column-clear instructions.

    Kept separate from Google API details so that building the plan is
    testable without any network calls.
    """

    clear_from_row: int
    clear_to_row: int
    clear_columns: list[int] = field(default_factory=list)
    value_updates: list[CellValueUpdate] = field(default_factory=list)

"""
pipeline.py – High-level processing workflow
==============================================
This is the **orchestration layer** — the only module that calls across
all sub-packages.  It should remain very small and read like a recipe:

  1. Resolve sheet headers → column indices.
  2. Build sales rows from sheet data.
  3. For each bill file: extract text → parse fields → assign to a row.
  4. Detect row-level conflicts.
  5. Build the write plan for Google Sheets.
  6. Write the review CSV.
  7. Return aggregated results.

No business decisions are made here — they are delegated to the
appropriate module in ``domain/``, ``extraction/``, or ``validation/``.
"""
from __future__ import annotations

from pathlib import Path

from insurance_rto_updater.domain.assignment import (
    Assignment,
    ReviewRow,
    assign_bill_to_row,
    assign_bill_to_row_by_filename_first_name,
    detect_row_conflicts,
)
from insurance_rto_updater.extraction.file_router import extract_text_from_file
from insurance_rto_updater.extraction.text_parser import (
    extract_customer,
    extract_final_amount,
    extract_insurance_report_rows,
)
from insurance_rto_updater.models import (
    BillParseResult,
    ProcessingConfig,
    ProcessingResult,
    SheetWritePlan,
)
from insurance_rto_updater.output.csv_writer import write_review_csv
from insurance_rto_updater.validation.comparator import (
    build_sales_rows,
    build_sheet_write_plan,
    find_header_indices,
    split_assignments_for_write,
)


# ---------------------------------------------------------------------------
# Internal: extract + parse a single bill
# ---------------------------------------------------------------------------

def _parse_bill_entries(
    bill_type: str,
    path: Path,
    config: ProcessingConfig,
) -> list[BillParseResult]:
    """
    Extract text from a bill file and parse one or more bill entries.

    Standard insurance / RTO uploads yield a single ``BillParseResult``.
    Insurance MIS reports may yield multiple per-customer results.
    """
    try:
        raw_text = extract_text_from_file(path)
    except Exception as exc:
        return [
            BillParseResult(
                bill_type=bill_type,
                file_name=path.name,
                extraction_error=f"TEXT_EXTRACTION_ERROR: {exc}",
            )
        ]

    if bill_type == "insurance":
        report_rows = extract_insurance_report_rows(raw_text, path.name)
        if report_rows is not None:
            return report_rows

    customer_name, customer_error = extract_customer(
        raw_text, config.customer_labels
    )
    amount, amount_error = extract_final_amount(
        raw_text, config.amount_labels, config.amount_position
    )

    return [
        BillParseResult(
            bill_type=bill_type,
            file_name=path.name,
            raw_text=raw_text,
            customer_name=customer_name,
            amount=amount,
            customer_error=customer_error,
            amount_error=amount_error,
        )
    ]


def _bill_to_review_row(bill: BillParseResult) -> ReviewRow:
    """Convert a failed bill parse to a ReviewRow for the conflict CSV."""
    reasons = [
        r
        for r in [
            bill.extraction_error,
            bill.customer_error,
            bill.amount_error,
        ]
        if r is not None
    ]
    return ReviewRow(
        bill_type=bill.bill_type,
        bill_file=bill.file_name,
        extracted_customer=bill.customer_name or "",
        extracted_amount=str(bill.amount) if bill.amount is not None else "",
        best_score="",
        candidate_sales_rows="",
        reason="; ".join(reasons),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_processing_pipeline(
    header_row: list[str],
    data_rows: list[list[str]],
    insurance_paths: list[Path],
    rto_paths: list[Path],
    output_dir: Path,
    config: ProcessingConfig,
    sheet_reference: str,
    sheet_title: str,
) -> tuple[ProcessingResult, SheetWritePlan]:
    """
    Execute the full bill-processing pipeline.

    This is the single entry point called by the Flask app.

    Steps
    -----
    1. **Resolve headers** – map user header names to column indices.
    2. **Build sales rows** – load customer names from the sheet.
    3. **Extract and parse** – OCR each bill file and parse fields.
    4. **Match and assign** – fuzzy-match each bill to a sales row.
    5. **Detect conflicts** – flag duplicate row/type claims.
    6. **Build write plan** – prepare batch cell updates.
    7. **Write review CSV** – persist unresolved cases for manual review.

    Returns
    -------
    (ProcessingResult, SheetWritePlan):
        The result summary (for the web UI) and the write plan (for the
        Google Sheets adapter).
    """
    # Step 1: resolve column indices from header names.
    customer_col, insurance_col, rto_col = find_header_indices(
        header_row=header_row,
        customer_header=config.customer_header,
        insurance_header=config.insurance_header,
        rto_header=config.rto_header,
    )

    # Step 2: build sales rows from sheet data.
    sales_rows, max_row = build_sales_rows(data_rows, customer_col)
    if not sales_rows:
        raise ValueError("No sales rows found with customer values.")

    # Step 3: combine all bill paths into a typed list.
    bill_specs = (
        [("insurance", p) for p in insurance_paths]
        + [("rto", p) for p in rto_paths]
    )

    # Steps 3–4: extract, parse, and assign each bill.
    review_rows: list[ReviewRow] = []
    assignments: list[Assignment] = []
    bills_processed = 0
    parse_failures = 0
    no_match = 0
    multi_match = 0

    for bill_type, path in bill_specs:
        for bill in _parse_bill_entries(bill_type, path, config):
            bills_processed += 1

            # If extraction or parsing failed, send straight to review.
            if bill.extraction_error or bill.amount_error:
                parse_failures += 1
                review_rows.append(_bill_to_review_row(bill))
                continue

            if bill.customer_error:
                if bill.customer_error == "CUSTOMER_LABEL_NOT_FOUND":
                    filename_assignment = assign_bill_to_row_by_filename_first_name(
                        bill,
                        sales_rows,
                    )
                    if filename_assignment is not None:
                        assignments.append(filename_assignment)
                        continue

                parse_failures += 1
                review_rows.append(_bill_to_review_row(bill))
                continue

            # Attempt to assign this bill to a sheet row.
            result = assign_bill_to_row(bill, sales_rows, config.name_threshold)

            if isinstance(result, Assignment):
                assignments.append(result)
            else:
                # result is a ReviewRow — track the specific failure type.
                if result.reason == "NO_MATCH":
                    no_match += 1
                elif result.reason == "MULTIPLE_SALES_ROWS":
                    multi_match += 1
                review_rows.append(result)

    # Step 5: detect row-level conflicts (multiple bills → same row+type).
    accepted, conflict_reviews = detect_row_conflicts(assignments)
    row_conflicts = sum(
        len(r.bill_file.split(", ")) for r in conflict_reviews
    )
    review_rows.extend(conflict_reviews)

    writable_assignments, preserved_reviews = split_assignments_for_write(
        accepted_assignments=accepted,
        data_rows=data_rows,
        insurance_col=insurance_col,
        rto_col=rto_col,
        clear_existing=config.clear_existing,
    )
    review_rows.extend(preserved_reviews)

    # Step 6: build the sheet write plan.
    write_plan = build_sheet_write_plan(
        accepted_assignments=writable_assignments,
        insurance_col=insurance_col,
        rto_col=rto_col,
        max_row=max_row,
        clear_existing=config.clear_existing,
    )

    # Step 7: write the review CSV.
    review_csv_path = write_review_csv(output_dir, review_rows)

    # Aggregate result summary.
    rows_updated = len({a.row_index for a in writable_assignments})

    processing_result = ProcessingResult(
        review_csv_path=review_csv_path,
        review_rows=review_rows,
        bills_processed=bills_processed,
        bills_updated=len(writable_assignments),
        rows_updated=rows_updated,
        bills_review=len(review_rows),
        parse_failures=parse_failures,
        no_match=no_match,
        multi_match=multi_match,
        row_conflicts=row_conflicts,
        sheet_reference=sheet_reference,
        sheet_title=sheet_title,
    )

    return processing_result, write_plan

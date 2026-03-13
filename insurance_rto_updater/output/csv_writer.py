"""
csv_writer.py – Review CSV generation
======================================
Writes the list of ``ReviewRow`` records to a CSV file that the user
can download and inspect.

The CSV reports bills that could not be confidently matched:
  - Parse failures (OCR errors or missing fields).
  - No customer match above the threshold.
  - Multiple equally-good matches.
  - Multiple bills claiming the same sheet row + bill type.

This module has **no** business logic — it only serializes data.
"""
from __future__ import annotations

import csv
from pathlib import Path

from insurance_rto_updater.models import ReviewRow

# Column order for the review CSV (matches the result.html template).
_FIELDNAMES = [
    "bill_type",
    "bill_file",
    "extracted_customer",
    "extracted_amount",
    "best_score",
    "candidate_sales_rows",
    "reason",
]


def write_review_csv(
    output_dir: Path,
    review_rows: list[ReviewRow],
) -> Path:
    """
    Write review rows to ``output_dir/review_conflicts.csv``.

    Creates ``output_dir`` if it does not exist.

    Returns the path to the generated CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    review_csv_path = output_dir / "review_conflicts.csv"

    with review_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for row in review_rows:
            writer.writerow(
                {
                    "bill_type": row.bill_type,
                    "bill_file": row.bill_file,
                    "extracted_customer": row.extracted_customer,
                    "extracted_amount": row.extracted_amount,
                    "best_score": row.best_score,
                    "candidate_sales_rows": row.candidate_sales_rows,
                    "reason": row.reason,
                }
            )

    return review_csv_path

"""
assignment.py – Bill → sheet-row assignment with conflict detection
===================================================================
This is the core **domain decision** module.  Given the scored candidates
for each bill, it decides:

  - **Accept**: exactly one candidate above threshold (or safe-fallback).
  - **Review (NO_MATCH)**: no candidate above threshold and no safe-fallback.
  - **Review (MULTIPLE_SALES_ROWS)**: more than one candidate above threshold.
  - **Review (MULTIPLE_BILLS_FOR_ROW_TYPE)**: two bills claim the same sheet
    row for the same bill type (insurance or RTO).

Safe-fallback heuristic
-----------------------
Even if no candidate reaches the configured threshold, we accept a match
when:
  - The top score is ≥ 80 (a reasonable baseline for Indian names).
  - The gap between the #1 and #2 candidates is ≥ 10 points (eliminates
    ambiguity).

This balances precision (avoiding wrong updates) with recall (not sending
obviously-correct matches to manual review).

All functions are **pure** — they operate on immutable inputs and return
new data structures.
"""
from __future__ import annotations

from insurance_rto_updater.models import (
    Assignment,
    BillParseResult,
    ReviewRow,
    SalesRow,
)
from insurance_rto_updater.domain.matching import (
    score_all_candidates,
    serialize_candidates,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum score for the safe-fallback heuristic.
_SAFE_FALLBACK_FLOOR = 80.0

# Required margin between #1 and #2 for safe-fallback to kick in.
_SAFE_FALLBACK_GAP = 10.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assign_bill_to_row(
    bill: BillParseResult,
    sales_rows: list[SalesRow],
    name_threshold: float,
) -> Assignment | ReviewRow:
    """
    Decide which sheet row a single bill should update.

    Parameters
    ----------
    bill:
        Successfully parsed bill (customer_name and amount must be set).
    sales_rows:
        All sales rows from the sheet.
    name_threshold:
        User-configured similarity cutoff (0–100).

    Returns
    -------
    Assignment:
        If exactly one unambiguous match is found.
    ReviewRow:
        If the bill cannot be confidently assigned (needs manual review).
    """
    assert bill.customer_name is not None
    assert bill.amount is not None

    scored = score_all_candidates(bill.customer_name, sales_rows)
    above_threshold = [
        (row, score) for row, score in scored if score >= name_threshold
    ]

    # --- Case 1: no candidate above threshold ----
    if not above_threshold:
        return _try_safe_fallback_or_review(bill, scored)

    # --- Case 2: multiple candidates above threshold ----
    if len(above_threshold) > 1:
        return ReviewRow(
            bill_type=bill.bill_type,
            bill_file=bill.file_name,
            extracted_customer=bill.customer_name,
            extracted_amount=str(bill.amount),
            best_score=f"{above_threshold[0][1]:.2f}",
            candidate_sales_rows=serialize_candidates(above_threshold),
            reason="MULTIPLE_SALES_ROWS",
        )

    # --- Case 3: exactly one candidate ----
    selected_row, score = above_threshold[0]
    return Assignment(
        bill_type=bill.bill_type,
        bill_file=bill.file_name,
        row_index=selected_row.row_index,
        amount=bill.amount,
        matched_customer=selected_row.customer_raw,
        score=score,
    )


def detect_row_conflicts(
    assignments: list[Assignment],
) -> tuple[list[Assignment], list[ReviewRow]]:
    """
    Check for multiple bills claiming the same (row, bill_type) slot.

    Insurance and RTO are treated independently — a row may have one
    insurance bill *and* one RTO bill without conflict.

    Returns
    -------
    accepted:
        Assignments with no conflicts.
    conflict_reviews:
        ReviewRows for conflicting assignments.
    """
    by_key: dict[tuple[int, str], list[Assignment]] = {}
    for assignment in assignments:
        key = (assignment.row_index, assignment.bill_type)
        by_key.setdefault(key, []).append(assignment)

    accepted: list[Assignment] = []
    conflict_reviews: list[ReviewRow] = []

    for (row_idx, bill_type), values in by_key.items():
        if len(values) == 1:
            accepted.append(values[0])
            continue

        conflict_reviews.append(
            ReviewRow(
                bill_type=bill_type,
                bill_file=", ".join(v.bill_file for v in values),
                extracted_customer=values[0].matched_customer,
                extracted_amount=", ".join(str(v.amount) for v in values),
                best_score=", ".join(f"{v.score:.2f}" for v in values),
                candidate_sales_rows=f"row={row_idx}",
                reason="MULTIPLE_BILLS_FOR_ROW_TYPE",
            )
        )

    return accepted, conflict_reviews


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _try_safe_fallback_or_review(
    bill: BillParseResult,
    scored: list[tuple[SalesRow, float]],
) -> Assignment | ReviewRow:
    """
    Apply the safe-fallback heuristic when no candidate meets the threshold.

    If the top candidate scores ≥ 80 *and* leads the runner-up by ≥ 10 points,
    accept it.  Otherwise, send to review.
    """
    if scored and scored[0][1] >= _SAFE_FALLBACK_FLOOR:
        top_row, top_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else 0.0

        if top_score - second_score >= _SAFE_FALLBACK_GAP:
            return Assignment(
                bill_type=bill.bill_type,
                bill_file=bill.file_name,
                row_index=top_row.row_index,
                amount=bill.amount,  # type: ignore[arg-type]
                matched_customer=top_row.customer_raw,
                score=top_score,
            )

    return ReviewRow(
        bill_type=bill.bill_type,
        bill_file=bill.file_name,
        extracted_customer=bill.customer_name or "",
        extracted_amount=str(bill.amount) if bill.amount is not None else "",
        best_score=f"{scored[0][1]:.2f}" if scored else "",
        candidate_sales_rows=(
            serialize_candidates(scored[:3]) if scored else ""
        ),
        reason="NO_MATCH",
    )

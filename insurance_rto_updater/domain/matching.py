"""
matching.py – Fuzzy name matching and candidate scoring
========================================================
Responsible for comparing an extracted customer name against every row
in the sales sheet and producing a ranked list of candidates.

Key design decision — **single scoring function**:
  The original codebase had two near-identical functions
  (``choose_sales_candidates`` and ``score_sales_rows``).  This module
  merges them into a single ``score_all_candidates`` function to eliminate
  duplication and make the scoring algorithm easy to tune in one place.

Scoring strategy
----------------
1. If ``rapidfuzz`` is installed (recommended), use its ``WRatio`` and
   ``token_set_ratio`` algorithms — both are designed for short strings
   with potential word-order variation.
2. Fallback: stdlib ``SequenceMatcher`` × 100 (same 0–100 scale).
3. Token-overlap bonus: if ≥ 80% of the query tokens appear verbatim in
   the candidate, the overlap ratio × 100 is used as an alternative score.
   This catches exact-token matches that fuzzy algorithms may under-score.

All functions are **pure** — they take data in and return data out with
no side effects.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable

from insurance_rto_updater.domain.normalization import normalize_customer_name
from insurance_rto_updater.models import SalesRow

# rapidfuzz is optional but strongly recommended for production use.
try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:
    _fuzz = None  # type: ignore[assignment]


def score_all_candidates(
    extracted_customer: str,
    sales_rows: list[SalesRow],
) -> list[tuple[SalesRow, float]]:
    """
    Score every sales row against the extracted customer name.

    Returns a list of ``(SalesRow, score)`` tuples sorted by descending
    score.  The caller decides the threshold for acceptance.

    Parameters
    ----------
    extracted_customer:
        The customer name parsed from the bill text.
    sales_rows:
        All sales rows loaded from the Google Sheet.
    """
    query_norm = normalize_customer_name(extracted_customer)
    query_tokens = set(query_norm.split())
    scored: list[tuple[SalesRow, float]] = []

    for row in sales_rows:
        # Primary fuzzy score.
        if _fuzz is not None:
            wratio = float(_fuzz.WRatio(query_norm, row.customer_norm))
            token_set = float(
                _fuzz.token_set_ratio(query_norm, row.customer_norm)
            )
            score = max(wratio, token_set)
        else:
            score = (
                SequenceMatcher(None, query_norm, row.customer_norm).ratio()
                * 100
            )

        # Token-overlap bonus: catches exact-token matches that fuzzy
        # algorithms may under-weight (e.g. "ANSHU SINGH" vs "ANSHU SINGH").
        row_tokens = set(row.customer_norm.split())
        if query_tokens and row_tokens:
            overlap = len(query_tokens & row_tokens) / max(
                1, len(query_tokens)
            )
            if overlap >= 0.80:
                score = max(score, overlap * 100)

        scored.append((row, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def serialize_candidates(
    candidates: Iterable[tuple[SalesRow, float]],
) -> str:
    """
    Format scored candidates as a human-readable summary for the review CSV.

    Example output:
        ``row=2,score=97.50,customer=ANSHU SINGH | row=5,score=82.10,...``
    """
    parts: list[str] = []
    for row, score in candidates:
        parts.append(
            f"row={row.row_index},score={score:.2f},"
            f"customer={row.customer_raw}"
        )
    return " | ".join(parts)

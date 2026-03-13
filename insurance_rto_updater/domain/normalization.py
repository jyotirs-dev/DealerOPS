"""
normalization.py – Text normalization utilities
================================================
Pure, deterministic functions for cleaning and normalizing text values
used throughout the pipeline.

These are intentionally small and composable — the ``normalize_text``
function is the most-called utility in the entire codebase.
"""
from __future__ import annotations

import re

# Pre-compiled pattern: collapses non-alphanumeric sequences into spaces.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    """
    Lowercase, strip non-alphanumeric characters, and collapse whitespace.

    Used uniformly for:
      - Header name comparison (sheet columns).
      - Customer name comparison (fuzzy matching prep).
      - Label matching in the text parser.

    Examples
    --------
    >>> normalize_text("   ANSHU  Singh—Sisodiya  ")
    'anshu singh sisodiya'
    >>> normalize_text("Insurance Amount")
    'insurance amount'
    """
    value = value.lower()
    value = _NON_ALNUM_RE.sub(" ", value)
    return " ".join(value.split())

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
_RELATIONSHIP_SUFFIX_RE = re.compile(
    r"\b(?:w\s*/\s*o|s\s*/\s*o|c\s*/\s*o)\b",
    flags=re.IGNORECASE,
)


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


def has_relationship_suffix(value: str) -> bool:
    """Return ``True`` when the text contains W/O, S/O, or C/O."""
    return bool(_RELATIONSHIP_SUFFIX_RE.search(value))


def strip_relationship_suffix(value: str) -> str:
    """Keep only the portion before W/O, S/O, or C/O."""
    trimmed = value.strip()
    if not trimmed:
        return ""
    head = _RELATIONSHIP_SUFFIX_RE.split(trimmed, maxsplit=1)[0]
    return " ".join(head.split())


def normalize_customer_name(value: str) -> str:
    """Normalize customer names after removing W/O, S/O, or C/O suffixes."""
    return normalize_text(strip_relationship_suffix(value))

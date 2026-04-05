"""
text_parser.py – Extract structured fields from raw bill text
=============================================================
Given the OCR output of an insurance or RTO bill, this module locates
two critical pieces of information:

1. **Customer name** – identified by scanning for user-supplied labels
   (e.g. "Insured", "Received From") and extracting the adjacent text.
2. **Final payable amount** – identified by amount labels (e.g. "Grand Total",
   "Final Amount") and extracted as a ``Decimal``.

Business rules encoded here
----------------------------
- Labels are matched fuzzily (≥ 75 % of label tokens must match at ≥ 0.80
  character similarity) to tolerate OCR noise.
- Customer names go through a refinement pipeline that strips titles
  (Mr/Mrs/Ms) and removes false-positive keywords common on insurance docs.
- Amounts are validated to have ≤ 7 digits (rejects policy numbers, phone
  numbers) and be ≥ ₹10 (rejects trivial stamp-duty values).
- When multiple amount candidates share the same label, the most-frequent
  value wins.  A tie is flagged as ``MULTIPLE_FINAL_AMOUNTS_FOUND``.

All functions are **pure** (no side effects, no shared state).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from insurance_rto_updater.domain.normalization import (
    has_relationship_suffix,
    normalize_text,
    strip_relationship_suffix,
)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Matches Indian-style currency amounts: 1,00,000 or 12345 or 1,234.56
AMOUNT_RE = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?(?!\d)"
)

# ---------------------------------------------------------------------------
# Internal helpers — label matching
# ---------------------------------------------------------------------------

def _fuzzy_label_match(line: str, label: str) -> bool:
    """
    Return ``True`` if *label* appears in *line*, tolerating OCR noise.

    Matching strategy:
      1. Exact substring match (fast path).
      2. Token-level fuzzy match — at least 75 % of label tokens must have
         a ≥ 0.80 SequenceMatcher ratio against some token in the line.

    This handles typical OCR errors like "Recelved" for "Received" or
    "lnsured" for "Insured".
    """
    normalized_line = normalize_text(line)
    normalized_label = normalize_text(label)
    if not normalized_line or not normalized_label:
        return False

    # Fast path: exact substring.
    if normalized_label in normalized_line:
        return True

    # Fuzzy token-level comparison.
    line_tokens = normalized_line.split()
    label_tokens = normalized_label.split()
    if not line_tokens or not label_tokens:
        return False

    required_matches = max(1, round(len(label_tokens) * 0.75))
    matched = sum(
        1
        for label_token in label_tokens
        if any(
            SequenceMatcher(None, label_token, line_token).ratio() >= 0.80
            for line_token in line_tokens
        )
    )
    return matched >= required_matches


# ---------------------------------------------------------------------------
# Internal helpers — customer name extraction
# ---------------------------------------------------------------------------

def _next_nonempty_line(lines: list[str], start_idx: int) -> str:
    """Return the first non-blank line at or after *start_idx*, or ``""``."""
    for idx in range(start_idx, len(lines)):
        candidate = lines[idx].strip()
        if candidate:
            return candidate
    return ""


def _sanitize_customer_text(value: str) -> str:
    """Collapse whitespace and strip leading punctuation from a raw name."""
    value = re.sub(r"[\t\r\n]+", " ", value)
    value = re.sub(r"^[\s:\-]+", "", value)
    return " ".join(value.split())

def _parse_customer_tail(line: str, label: str) -> str:
    """
    Extract the customer name that follows *label* on the same *line*.

    Tries (in order):
      1. Literal substring match → take everything after the label.
      2. Colon-separated → take the right side of the first ``:``.
      3. Pipe-separated → take the right side of the first ``|``.
      4. Word-count heuristic → drop the first N words that match the label.
    """
    lowered_line = line.lower()
    lowered_label = label.lower().strip()

    if lowered_label in lowered_line:
        start = lowered_line.find(lowered_label) + len(lowered_label)
        return _sanitize_customer_text(line[start:])

    if ":" in line:
        return _sanitize_customer_text(line.split(":", 1)[1])
    if "|" in line:
        return _sanitize_customer_text(line.split("|", 1)[1])

    words = line.split()
    label_word_count = max(1, len(label.split()))
    if len(words) <= label_word_count:
        return ""
    return _sanitize_customer_text(" ".join(words[label_word_count:]))


def _refine_customer_name(value: str) -> str:
    """
    Clean up a raw customer-name candidate.

    Handles patterns like:
      - "from Mr Ramesh Kumar as ..." → "Ramesh Kumar"
      - "Mr. Anshu Singh" → "Anshu Singh"
    """
    cleaned = strip_relationship_suffix(_sanitize_customer_text(value))

    # Pattern: "from <title> NAME as ..."
    from_match = re.search(
        r"\bfrom\s+(?:mr|mrs|ms|m)?\.?\s*([a-zA-Z ]+?)(?:\s+as\b|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if from_match:
        return _sanitize_customer_text(from_match.group(1))

    # Pattern: "<title> NAME"
    title_match = re.search(
        r"\b(?:mr|mrs|ms|m)\.?\s+([a-zA-Z ]+)$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if title_match:
        return _sanitize_customer_text(title_match.group(1))

    return cleaned


def _normalize_customer_candidate(value: str) -> str:
    """Normalize a candidate name for de-duplication (strip titles + lowercase)."""
    normalized = normalize_text(value)
    # Remove common Indian honorifics that vary across bill formats.
    normalized = re.sub(r"^(mr|mrs|ms|m)\s+", "", normalized)
    return normalized.strip()


# Keywords that appear on insurance documents but are NOT customer names.
_BLOCKED_WORDS = frozenset({
    "optional", "cover", "passenger", "driver", "premium", "policy",
    "insured", "liability", "indemnified", "notice", "sum", "unnamed",
    "received", "thanks", "against", "receipt", "company", "stamp",
    "duty", "bank", "business", "profession", "address", "period",
    "office", "important", "clause", "headed", "see",
})

# Generic stop words that alone do not constitute a name.
_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "to", "in", "on", "by",
    "as", "any", "not", "sae", "reason",
})


def _is_likely_customer_name(
    value: str, *, allow_single_word: bool = False
) -> bool:
    """
    Heuristic filter to reject text that *looks like* a customer name
    but is actually an insurance field label or boilerplate.

    Rules:
      - Must be 2–6 alphabetic words (or 1–6 after relationship trimming).
      - No word may be shorter than 2 characters.
      - Must not contain any blocked insurance keywords.
      - Must not consist entirely of stop words.
    """
    compact = re.sub(r"[^a-zA-Z ]", " ", value)
    compact = " ".join(compact.split())
    if not compact:
        return False

    words = compact.lower().split()
    min_words = 1 if allow_single_word else 2
    if len(words) < min_words or len(words) > 6:
        return False
    if any(len(word) < 2 for word in words):
        return False
    if any(word in _BLOCKED_WORDS for word in words):
        return False
    if all(word in _STOP_WORDS for word in words):
        return False

    return True


# ---------------------------------------------------------------------------
# Internal helpers — amount extraction
# ---------------------------------------------------------------------------

def _extract_amount_candidates(text: str) -> list[Decimal]:
    """
    Find all plausible currency amounts in a text fragment.

    Filters out values with more than 7 digits (likely policy/phone numbers).
    """
    candidates: list[Decimal] = []
    for token in AMOUNT_RE.findall(text):
        cleaned = token.replace(",", "")
        digit_count = len(re.sub(r"\D", "", cleaned))
        if digit_count > 7:
            continue
        try:
            amount = Decimal(cleaned)
        except InvalidOperation:
            continue
        candidates.append(amount)
    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_customer(
    text: str,
    customer_labels: list[str],
) -> tuple[str | None, str | None]:
    """
    Locate the customer name in the raw bill text.

    Scans lines for any of the supplied *customer_labels* (fuzzy match),
    then extracts the adjacent text, refines it, and validates it.

    Returns
    -------
    (customer_name, None)     – on success.
    (None, error_reason)      – on failure (e.g. label not found, multiple
                                unresolvable candidates).
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, "EMPTY_TEXT"

    candidates: list[str] = []
    lower_labels = [
        label.lower().strip() for label in customer_labels if label.strip()
    ]

    for idx, line in enumerate(lines):
        for label in lower_labels:
            if not _fuzzy_label_match(line, label):
                continue

            # Try same-line extraction first.
            same_line_raw = _parse_customer_tail(line, label)
            same_line_part = _refine_customer_name(same_line_raw)
            if same_line_part and _is_likely_customer_name(
                same_line_part,
                allow_single_word=has_relationship_suffix(same_line_raw),
            ):
                candidates.append(same_line_part)
                continue

            # Fall back to the next non-empty line.
            next_line_raw = _next_nonempty_line(lines, idx + 1)
            next_line = _refine_customer_name(next_line_raw)
            if next_line and _is_likely_customer_name(
                next_line,
                allow_single_word=has_relationship_suffix(next_line_raw),
            ):
                candidates.append(next_line)

    # De-duplicate while preserving insertion order.
    unique = list(dict.fromkeys(candidates))
    if not unique:
        return None, "CUSTOMER_LABEL_NOT_FOUND"

    # Filter to truly distinct normalized forms.
    resolved: list[str] = []
    seen_norm: set[str] = set()
    for candidate in unique:
        normalized = _normalize_customer_candidate(candidate)
        if not normalized or normalized in seen_norm:
            continue
        seen_norm.add(normalized)
        resolved.append(candidate)

    if len(resolved) == 1:
        return resolved[0], None

    if not resolved:
        return None, "CUSTOMER_LABEL_NOT_FOUND"

    # Multiple candidates — accept if they are all similar (OCR variants).
    best = max(
        resolved, key=lambda item: len(_normalize_customer_candidate(item))
    )
    best_norm = _normalize_customer_candidate(best)
    all_similar = all(
        SequenceMatcher(
            None, best_norm, _normalize_customer_candidate(other)
        ).ratio()
        >= 0.88
        for other in resolved
    )
    if all_similar:
        return best, None

    return None, "MULTIPLE_CUSTOMER_CANDIDATES"


def extract_final_amount(
    text: str,
    amount_labels: list[str],
    amount_position: str,
) -> tuple[Decimal | None, str | None]:
    """
    Locate the final payable amount in the raw bill text.

    For each *amount_label*, search lines for a fuzzy match, then:
      - ``same_line`` mode: extract amounts from the remainder of the line.
      - ``next_line`` mode: extract amounts from the line immediately after.

    Amounts below ₹10 are discarded (stamp duty, token values).

    When a label yields multiple distinct amounts, the most-frequent value
    wins.  A tie is flagged as ``MULTIPLE_FINAL_AMOUNTS_FOUND``.

    Returns
    -------
    (amount, None)          – on success.
    (None, error_reason)    – on failure.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, "EMPTY_TEXT"

    lower_labels = [
        label.lower().strip() for label in amount_labels if label.strip()
    ]

    for label in lower_labels:
        label_candidates: list[Decimal] = []

        for idx, line in enumerate(lines):
            if not _fuzzy_label_match(line, label):
                continue

            if amount_position == "same_line":
                # Try text *after* the label first, then the whole line.
                lowered = line.lower()
                if label in lowered:
                    start = lowered.find(label) + len(label)
                    tail = line[start:]
                else:
                    tail = line
                extracted = _extract_amount_candidates(tail)
                if not extracted:
                    extracted = _extract_amount_candidates(line)
                label_candidates.extend(
                    v for v in extracted if v >= Decimal("10")
                )

            elif amount_position == "next_line":
                line_after = _next_nonempty_line(lines, idx + 1)
                next_values = _extract_amount_candidates(line_after)
                label_candidates.extend(
                    v for v in next_values if v >= Decimal("10")
                )

            else:
                return None, "INVALID_AMOUNT_POSITION"

        if not label_candidates:
            continue

        # Pick the most-frequent amount; break ties by flagging ambiguity.
        freq: dict[Decimal, int] = {}
        for value in label_candidates:
            freq[value] = freq.get(value, 0) + 1

        ranked = sorted(freq.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) == 1:
            return ranked[0][0], None
        if ranked[0][1] > ranked[1][1]:
            return ranked[0][0], None

        return None, "MULTIPLE_FINAL_AMOUNTS_FOUND"

    return None, "FINAL_AMOUNT_LABEL_NOT_FOUND"

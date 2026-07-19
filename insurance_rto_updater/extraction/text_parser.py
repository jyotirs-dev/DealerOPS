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

import logging
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from insurance_rto_updater.domain.normalization import normalize_text
from insurance_rto_updater.models import BillParseResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Matches Indian-style currency amounts: 1,00,000 or 12345 or 1,234.56
AMOUNT_RE = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?(?!\d)"
)
_SERIAL_LINE_RE = re.compile(r"^\d+\.$")
_DATE_LINE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_POLICY_NUMBER_LINE_RE = re.compile(
    r"^(?P<policy_number>\d{10,})(?:\s+(?P<customer>.*\S))?$"
)
_WHOLE_AMOUNT_LINE_RE = re.compile(r"^\$?\d[\d,]*(?:\.\d{1,2})?$")
_INSURANCE_REPORT_MARKERS = (
    "mis business report user wise",
    "policy number",
    "gross premium",
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


def _clean_report_line(value: str) -> str:
    """Normalize whitespace in a PDF-extracted report line."""
    return " ".join(value.replace("\xa0", " ").split())

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
    cleaned = _sanitize_customer_text(value)

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
    "office", "important", "clause", "headed", "see", "amount", "total",
    "grand", "date", "vehicle", "registration", "motor", "number",
})

# Generic stop words that alone do not constitute a name.
_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "to", "in", "on", "by",
    "as", "any", "not", "sae", "reason",
})


def _is_likely_customer_name(value: str) -> bool:
    """
    Heuristic filter to reject text that *looks like* a customer name
    but is actually an insurance field label or boilerplate.

    Rules:
      - Must be 2–6 alphabetic words.
      - No word may be shorter than 2 characters.
      - Must not contain any blocked insurance keywords.
      - Must not consist entirely of stop words.
    """
    compact = re.sub(r"[^a-zA-Z ]", " ", value)
    compact = " ".join(compact.split())
    if not compact:
        return False

    words = compact.lower().split()
    if len(words) < 1 or len(words) > 6:
        return False
    if len(words) == 1 and len(words[0]) < 3:
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


def _looks_like_insurance_report(text: str) -> bool:
    """Return ``True`` when the text matches the MIS insurance report layout."""
    normalized = normalize_text(text.replace("\xa0", " "))
    return all(marker in normalized for marker in _INSURANCE_REPORT_MARKERS)


def _build_report_row_file_name(file_name: str, serial_number: str) -> str:
    """Tag review/update rows with the source file and report serial number."""
    return f"{file_name} [S.No. {serial_number}]"


def _extract_report_customer_name(record_lines: list[str], date_idx: int) -> str:
    """Extract the customer-name segment from one insurance report record."""
    policy_idx = next(
        (
            idx
            for idx, line in enumerate(record_lines[1:date_idx], start=1)
            if _POLICY_NUMBER_LINE_RE.match(line)
        ),
        None,
    )
    if policy_idx is None:
        return ""

    policy_match = _POLICY_NUMBER_LINE_RE.match(record_lines[policy_idx])
    assert policy_match is not None

    customer_parts: list[str] = []
    inline_customer = (policy_match.group("customer") or "").strip()
    if inline_customer:
        customer_parts.append(inline_customer)
    customer_parts.extend(record_lines[policy_idx + 1:date_idx])

    cleaned_parts: list[str] = []
    for part in customer_parts:
        cleaned = _sanitize_customer_text(part)
        cleaned = re.sub(r"\s*\.+\s*$", "", cleaned)
        if cleaned:
            cleaned_parts.append(cleaned)

    return _refine_customer_name(" ".join(cleaned_parts))


def _extract_report_gross_premium(record_lines: list[str], date_idx: int) -> Decimal | None:
    """Return the gross premium from one insurance report record."""
    for line in reversed(record_lines[date_idx + 1:]):
        cleaned = _clean_report_line(line).lstrip("$")
        if not _WHOLE_AMOUNT_LINE_RE.match(cleaned):
            continue
        try:
            amount = Decimal(cleaned.replace(",", ""))
        except InvalidOperation:
            continue
        if amount >= Decimal("10"):
            return amount
    return None


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
            if same_line_part and _is_likely_customer_name(same_line_part):
                candidates.append(same_line_part)
                continue

            # Fall back to the next non-empty line.
            next_line_raw = _next_nonempty_line(lines, idx + 1)
            next_line = _refine_customer_name(next_line_raw)
            if next_line and _is_likely_customer_name(next_line):
                candidates.append(next_line)

    # De-duplicate while preserving insertion order.
    unique = list(dict.fromkeys(candidates))
    if not unique:
        logger.warning(
            "CUSTOMER_LABEL_NOT_FOUND — no candidate extracted. "
            "labels_tried=%r  lines_scanned=%d  text_preview=%r",
            customer_labels,
            len(lines),
            text[:200],
        )
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
        logger.warning(
            "CUSTOMER_LABEL_NOT_FOUND — all candidates normalised to duplicates. "
            "labels_tried=%r  raw_candidates=%r",
            customer_labels,
            unique,
        )
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


def extract_insurance_report_rows(
    text: str,
    file_name: str,
) -> list[BillParseResult] | None:
    """
    Parse a multi-row insurance MIS report into per-customer bill records.

    Returns ``None`` when the text does not look like the report format so the
    caller can fall back to the standard single-bill parser.
    """
    if not _looks_like_insurance_report(text):
        return None

    lines = [
        cleaned
        for raw_line in text.splitlines()
        if (cleaned := _clean_report_line(raw_line))
    ]
    start_idx = next(
        (idx for idx, line in enumerate(lines) if _SERIAL_LINE_RE.match(line)),
        None,
    )
    if start_idx is None:
        return [
            BillParseResult(
                bill_type="insurance",
                file_name=file_name,
                raw_text=text,
                extraction_error="INSURANCE_REPORT_ROWS_NOT_FOUND",
            )
        ]

    records: list[list[str]] = []
    current_record: list[str] = []
    for line in lines[start_idx:]:
        if normalize_text(line).startswith("total"):
            break
        if _SERIAL_LINE_RE.match(line):
            if current_record:
                records.append(current_record)
            current_record = [line]
            continue
        if current_record:
            current_record.append(line)

    if current_record:
        records.append(current_record)

    if not records:
        return [
            BillParseResult(
                bill_type="insurance",
                file_name=file_name,
                raw_text=text,
                extraction_error="INSURANCE_REPORT_ROWS_NOT_FOUND",
            )
        ]

    results: list[BillParseResult] = []
    for record_lines in records:
        serial_number = record_lines[0].rstrip(".")
        date_idx = next(
            (
                idx
                for idx, line in enumerate(record_lines[1:], start=1)
                if _DATE_LINE_RE.match(line)
            ),
            None,
        )
        customer_name = ""
        customer_error: str | None = None
        amount = None
        amount_error: str | None = None

        if date_idx is None:
            customer_error = "INSURANCE_REPORT_DATE_NOT_FOUND"
            amount_error = "INSURANCE_REPORT_GROSS_PREMIUM_NOT_FOUND"
        else:
            customer_name = _extract_report_customer_name(record_lines, date_idx)
            if not customer_name or not _is_likely_customer_name(customer_name):
                customer_error = "INSURANCE_REPORT_CUSTOMER_NOT_FOUND"
                customer_name = ""

            amount = _extract_report_gross_premium(record_lines, date_idx)
            if amount is None:
                amount_error = "INSURANCE_REPORT_GROSS_PREMIUM_NOT_FOUND"

        results.append(
            BillParseResult(
                bill_type="insurance",
                file_name=_build_report_row_file_name(file_name, serial_number),
                raw_text="\n".join(record_lines),
                customer_name=customer_name or None,
                amount=amount,
                customer_error=customer_error,
                amount_error=amount_error,
            )
        )

    return results


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


def _looks_like_pay_in_slip(text: str) -> bool:
    """Return ``True`` when the text matches the HIBIPL Pay-in-slip layout."""
    normalized = normalize_text(text.replace("\xa0", " "))
    return all(marker in normalized for marker in ("pay in slip", "policy details", "premium"))


def extract_pay_in_slip_rows(
    text: str,
    file_name: str,
) -> list[BillParseResult] | None:
    """
    Parse a multi-row HIBIPL Pay-in-slip PDF into per-customer bill records.

    Returns ``None`` when the text does not look like the pay-in-slip format
    so the caller can fall back to the standard single-bill parser.
    """
    if not _looks_like_pay_in_slip(text):
        return None

    lines = [
        cleaned
        for raw_line in text.splitlines()
        if (cleaned := " ".join(raw_line.replace("\xa0", " ").split()).strip())
    ]

    # Find start of data (line '1' after 'policy details')
    start_idx = None
    policy_details_idx = None
    for idx, line in enumerate(lines):
        if "policy details" in line.lower():
            policy_details_idx = idx
            break

    if policy_details_idx is not None:
        for idx in range(policy_details_idx, len(lines)):
            if lines[idx] == "1":
                start_idx = idx
                break

    if start_idx is None:
        return [
            BillParseResult(
                bill_type="insurance",
                file_name=file_name,
                raw_text=text,
                extraction_error="PAY_IN_SLIP_ROWS_NOT_FOUND",
            )
        ]

    # Find end of data (line containing 'total amount')
    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if "total amount" in lines[idx].lower():
            end_idx = idx
            break

    data_lines = lines[start_idx:end_idx]

    # Group records by serial numbers
    serial_indices: list[int] = []
    next_serial = 1
    for idx, line in enumerate(data_lines):
        if line.strip() == str(next_serial):
            serial_indices.append(idx)
            next_serial += 1

    records: list[list[str]] = []
    for i in range(len(serial_indices)):
        start = serial_indices[i]
        end = serial_indices[i+1] if i + 1 < len(serial_indices) else len(data_lines)
        records.append(data_lines[start+1:end])

    if not records:
        return [
            BillParseResult(
                bill_type="insurance",
                file_name=file_name,
                raw_text=text,
                extraction_error="PAY_IN_SLIP_ROWS_NOT_FOUND",
            )
        ]

    date_pattern = re.compile(
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:\s+\d{4})?\b',
        re.IGNORECASE
    )
    year_pattern = re.compile(r'\b20\d{2}\b')
    status_pattern = re.compile(r'\b(?:Fresh|Renewal)\b', re.IGNORECASE)

    results: list[BillParseResult] = []
    for idx, record in enumerate(records, start=1):
        if len(record) < 4:
            results.append(
                BillParseResult(
                    bill_type="insurance",
                    file_name=f"{file_name} [S.No. {idx}]",
                    raw_text="\n".join(record),
                    extraction_error="PAY_IN_SLIP_RECORD_MALFORMED",
                )
            )
            continue

        policy_no = record[0].strip()
        premium_str = record[-1].strip()
        intermediate = record[1:-2]

        # Extract customer name
        merged = " ".join(intermediate)
        merged_no_date = date_pattern.sub("", merged)
        merged_no_year = year_pattern.sub("", merged_no_date)
        merged_no_status = status_pattern.sub("", merged_no_year)

        cleaned_name = merged_no_status.replace(".", " ").replace(",", " ")
        cleaned_name = " ".join(cleaned_name.split()).strip()

        # Title clean (matches Mr, Mrs, Ms honorifics)
        title_match = re.search(
            r"\b(?:mr|mrs|ms|m)\.?\s+([a-zA-Z ]+)$",
            cleaned_name,
            flags=re.IGNORECASE,
        )
        if title_match:
            customer_name = title_match.group(1).strip()
        else:
            customer_name = cleaned_name

        try:
            amount = Decimal(premium_str.replace(",", ""))
        except (InvalidOperation, ValueError):
            amount = None

        customer_error = None
        amount_error = None

        if not customer_name or not _is_likely_customer_name(customer_name):
            customer_error = "PAY_IN_SLIP_CUSTOMER_NOT_FOUND"
            customer_name = None

        if amount is None:
            amount_error = "PAY_IN_SLIP_PREMIUM_NOT_FOUND"

        results.append(
            BillParseResult(
                bill_type="insurance",
                file_name=f"{file_name} [S.No. {idx}]",
                raw_text="\n".join(record),
                customer_name=customer_name,
                amount=amount,
                customer_error=customer_error,
                amount_error=amount_error,
            )
        )

    return results


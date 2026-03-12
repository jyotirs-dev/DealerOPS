from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps
from sheets_adapter import CellValueUpdate, SheetWritePlan

try:
    import fitz
except ImportError:  # pragma: no cover - optional runtime dependency
    fitz = None  # type: ignore[assignment]

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - optional runtime dependency
    fuzz = None  # type: ignore[assignment]

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional runtime dependency
    pytesseract = None  # type: ignore[assignment]


AMOUNT_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?(?!\d)")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class ProcessingConfig:
    sheet_name: str | None
    customer_header: str
    insurance_header: str
    rto_header: str
    customer_labels: list[str]
    amount_labels: list[str]
    amount_position: str
    name_threshold: float
    clear_existing: bool


@dataclass
class SalesRow:
    row_index: int
    customer_raw: str
    customer_norm: str


@dataclass
class Assignment:
    bill_type: str
    bill_file: str
    row_index: int
    amount: Decimal
    matched_customer: str
    score: float


@dataclass
class ReviewRow:
    bill_type: str
    bill_file: str
    extracted_customer: str
    extracted_amount: str
    best_score: str
    candidate_sales_rows: str
    reason: str


@dataclass
class ProcessingResult:
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


def normalize_text(value: str) -> str:
    value = value.lower()
    value = NON_ALNUM_RE.sub(" ", value)
    return " ".join(value.split())


def extract_amount_candidates(text: str) -> list[Decimal]:
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


def find_header_indices(
    header_row: list[str], customer_header: str, insurance_header: str, rto_header: str
) -> tuple[int, int, int]:
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


def run_tesseract_cli(image_path: Path, psm: int) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeError("OCR engine not found. Install tesseract to process image/scanned bills.")

    command = ["tesseract", str(image_path), "stdout", "--psm", str(psm)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"Tesseract OCR failed: {stderr or 'unknown error'}")
    return result.stdout


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    gray = ImageOps.autocontrast(gray)
    scaled = gray.resize((gray.width * 3, gray.height * 3))
    return scaled.point(lambda pixel: 255 if pixel > 170 else 0)


def ocr_image(image: Image.Image) -> str:
    variants = [
        (preprocess_for_ocr(image), 11),
        (image.convert("RGB"), 6),
    ]

    for variant_image, psm in variants:
        if pytesseract is not None:
            text = pytesseract.image_to_string(variant_image, config=f"--psm {psm}")
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / "ocr_input.png"
                variant_image.convert("RGB").save(temp_path)
                text = run_tesseract_cli(temp_path, psm=psm)

        if text.strip():
            return text

    return ""


def extract_pdf_text_with_sips_ocr(path: Path) -> str:
    if shutil.which("sips") is None:
        raise RuntimeError(
            "PDF parser missing and sips fallback unavailable. Install PyMuPDF to read PDF bills."
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        png_path = Path(temp_dir) / "pdf_page.png"
        result = subprocess.run(
            ["sips", "-s", "format", "png", str(path), "--out", str(png_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not png_path.exists():
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"PDF to image conversion failed: {stderr or 'unknown error'}")

        rgba = Image.open(png_path).convert("RGBA")
        white_bg = Image.new("RGBA", rgba.size, "white")
        white_bg.alpha_composite(rgba)
        return ocr_image(white_bg.convert("RGB"))


def extract_pdf_text(path: Path) -> str:
    if fitz is None:
        return extract_pdf_text_with_sips_ocr(path)

    document = fitz.open(path)
    output_parts: list[str] = []
    try:
        for page in document:
            page_text = (page.get_text("text") or "").strip()
            if page_text:
                output_parts.append(page_text)
                continue

            matrix = fitz.Matrix(2, 2)
            pixmap = page.get_pixmap(matrix=matrix)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            ocr_text = ocr_image(image)
            if ocr_text.strip():
                output_parts.append(ocr_text)
    finally:
        document.close()

    merged = "\n".join(output_parts).strip()
    if not merged:
        raise RuntimeError("No readable text found in PDF.")
    return merged


def extract_image_text(path: Path) -> str:
    image = Image.open(path)
    text = ocr_image(image)
    if not text.strip():
        raise RuntimeError("No readable text found in image bill.")
    return text


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    return extract_image_text(path)


def next_nonempty_line(lines: list[str], start_idx: int) -> str:
    for idx in range(start_idx, len(lines)):
        candidate = lines[idx].strip()
        if candidate:
            return candidate
    return ""


def sanitize_customer_text(value: str) -> str:
    value = re.sub(r"[\t\r\n]+", " ", value)
    value = re.sub(r"^[\s:\-]+", "", value)
    value = " ".join(value.split())
    return value


def fuzzy_label_match(line: str, label: str) -> bool:
    normalized_line = normalize_text(line)
    normalized_label = normalize_text(label)
    if not normalized_line or not normalized_label:
        return False
    if normalized_label in normalized_line:
        return True

    line_tokens = normalized_line.split()
    label_tokens = normalized_label.split()
    if not line_tokens or not label_tokens:
        return False

    required_matches = max(1, round(len(label_tokens) * 0.75))
    matched = 0
    for label_token in label_tokens:
        token_hit = any(
            SequenceMatcher(None, label_token, line_token).ratio() >= 0.8
            for line_token in line_tokens
        )
        if token_hit:
            matched += 1
    return matched >= required_matches


def parse_customer_tail_from_line(line: str, label: str) -> str:
    lowered_line = line.lower()
    lowered_label = label.lower().strip()
    if lowered_label in lowered_line:
        start = lowered_line.find(lowered_label) + len(lowered_label)
        return sanitize_customer_text(line[start:])

    if ":" in line:
        return sanitize_customer_text(line.split(":", 1)[1])
    if "|" in line:
        return sanitize_customer_text(line.split("|", 1)[1])

    words = line.split()
    label_word_count = max(1, len(label.split()))
    if len(words) <= label_word_count:
        return ""
    return sanitize_customer_text(" ".join(words[label_word_count:]))


def normalize_customer_candidate(value: str) -> str:
    normalized = normalize_text(value)
    normalized = re.sub(r"^(mr|mrs|ms|m)\s+", "", normalized)
    return normalized.strip()


def refine_customer_name(value: str) -> str:
    cleaned = sanitize_customer_text(value)
    from_match = re.search(
        r"\bfrom\s+(?:mr|mrs|ms|m)?\.?\s*([a-zA-Z ]+?)(?:\s+as\b|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if from_match:
        return sanitize_customer_text(from_match.group(1))

    title_match = re.search(r"\b(?:mr|mrs|ms|m)\.?\s+([a-zA-Z ]+)$", cleaned, flags=re.IGNORECASE)
    if title_match:
        return sanitize_customer_text(title_match.group(1))

    return cleaned


def is_likely_customer_name(value: str) -> bool:
    compact = re.sub(r"[^a-zA-Z ]", " ", value)
    compact = " ".join(compact.split())
    if not compact:
        return False

    words = compact.lower().split()
    if len(words) < 2 or len(words) > 6:
        return False
    if any(len(word) < 2 for word in words):
        return False

    blocked = {
        "optional",
        "cover",
        "passenger",
        "driver",
        "premium",
        "policy",
        "insured",
        "liability",
        "indemnified",
        "notice",
        "sum",
        "unnamed",
        "received",
        "thanks",
        "against",
        "receipt",
        "company",
        "stamp",
        "duty",
        "bank",
        "business",
        "profession",
        "address",
        "policy",
        "period",
        "office",
        "important",
        "notice",
        "clause",
        "headed",
        "see",
    }
    if any(word in blocked for word in words):
        return False

    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "to",
        "in",
        "on",
        "by",
        "as",
        "any",
        "not",
        "sae",
        "reason",
    }
    if all(word in stop_words for word in words):
        return False

    return True


def extract_customer(text: str, customer_labels: list[str]) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, "EMPTY_TEXT"

    candidates: list[str] = []
    lower_labels = [label.lower().strip() for label in customer_labels if label.strip()]

    for idx, line in enumerate(lines):
        for label in lower_labels:
            if not fuzzy_label_match(line, label):
                continue

            same_line_part = parse_customer_tail_from_line(line, label)
            same_line_part = refine_customer_name(same_line_part)
            if same_line_part:
                if not is_likely_customer_name(same_line_part):
                    continue
                candidates.append(same_line_part)
                continue

            next_line = sanitize_customer_text(next_nonempty_line(lines, idx + 1))
            next_line = refine_customer_name(next_line)
            if next_line:
                if not is_likely_customer_name(next_line):
                    continue
                candidates.append(next_line)

    unique_candidates = list(dict.fromkeys(candidates))
    if not unique_candidates:
        return None, "CUSTOMER_LABEL_NOT_FOUND"

    resolved: list[str] = []
    seen_norm: set[str] = set()
    for candidate in unique_candidates:
        normalized = normalize_customer_candidate(candidate)
        if not normalized or normalized in seen_norm:
            continue
        seen_norm.add(normalized)
        resolved.append(candidate)

    if len(resolved) == 1:
        return resolved[0], None

    if not resolved:
        return None, "CUSTOMER_LABEL_NOT_FOUND"

    best = max(resolved, key=lambda item: len(normalize_customer_candidate(item)))
    best_norm = normalize_customer_candidate(best)
    similar = all(
        SequenceMatcher(None, best_norm, normalize_customer_candidate(other)).ratio() >= 0.88
        for other in resolved
    )
    if similar:
        return best, None

    return None, "MULTIPLE_CUSTOMER_CANDIDATES"


def extract_final_amount(
    text: str, amount_labels: list[str], amount_position: str
) -> tuple[Decimal | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, "EMPTY_TEXT"

    lower_labels = [label.lower().strip() for label in amount_labels if label.strip()]

    for label in lower_labels:
        label_candidates: list[Decimal] = []
        for idx, line in enumerate(lines):
            if not fuzzy_label_match(line, label):
                continue

            if amount_position == "same_line":
                lowered_line = line.lower()
                if label in lowered_line:
                    start = lowered_line.find(label) + len(label)
                    line_tail = line[start:]
                else:
                    line_tail = line
                extracted = extract_amount_candidates(line_tail)
                if not extracted:
                    extracted = extract_amount_candidates(line)
                label_candidates.extend(value for value in extracted if value >= Decimal("10"))
            elif amount_position == "next_line":
                line_after = next_nonempty_line(lines, idx + 1)
                next_line_values = extract_amount_candidates(line_after)
                label_candidates.extend(value for value in next_line_values if value >= Decimal("10"))
            else:
                return None, "INVALID_AMOUNT_POSITION"

        if not label_candidates:
            continue

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


def choose_sales_candidates(
    extracted_customer: str, sales_rows: list[SalesRow], threshold: float
) -> list[tuple[SalesRow, float]]:
    query_norm = normalize_text(extracted_customer)
    query_tokens = set(query_norm.split())
    scored: list[tuple[SalesRow, float]] = []

    for row in sales_rows:
        base_score: float
        if fuzz is not None:
            wratio = float(fuzz.WRatio(query_norm, row.customer_norm))
            token_set = float(fuzz.token_set_ratio(query_norm, row.customer_norm))
            base_score = max(wratio, token_set)
        else:
            base_score = SequenceMatcher(None, query_norm, row.customer_norm).ratio() * 100

        row_tokens = set(row.customer_norm.split())
        if query_tokens and row_tokens:
            overlap = len(query_tokens & row_tokens) / max(1, len(query_tokens))
            if overlap >= 0.8:
                base_score = max(base_score, overlap * 100)

        score = base_score
        if score >= threshold:
            scored.append((row, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def score_sales_rows(
    extracted_customer: str,
    sales_rows: list[SalesRow],
) -> list[tuple[SalesRow, float]]:
    query_norm = normalize_text(extracted_customer)
    query_tokens = set(query_norm.split())
    scored: list[tuple[SalesRow, float]] = []
    for row in sales_rows:
        if fuzz is not None:
            wratio = float(fuzz.WRatio(query_norm, row.customer_norm))
            token_set = float(fuzz.token_set_ratio(query_norm, row.customer_norm))
            score = max(wratio, token_set)
        else:
            score = SequenceMatcher(None, query_norm, row.customer_norm).ratio() * 100

        row_tokens = set(row.customer_norm.split())
        if query_tokens and row_tokens:
            overlap = len(query_tokens & row_tokens) / max(1, len(query_tokens))
            if overlap >= 0.8:
                score = max(score, overlap * 100)

        scored.append((row, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def serialize_candidates(candidates: Iterable[tuple[SalesRow, float]]) -> str:
    parts: list[str] = []
    for row, score in candidates:
        parts.append(f"row={row.row_index},score={score:.2f},customer={row.customer_raw}")
    return " | ".join(parts)


def build_sales_rows(data_rows: list[list[str]], customer_col: int) -> tuple[list[SalesRow], int]:
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
                customer_norm=normalize_text(customer_raw),
            )
        )

    max_row = len(data_rows) + 1
    return sales_rows, max_row


def write_review_csv(output_dir: Path, review_rows: list[ReviewRow]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    review_csv_path = output_dir / "review_conflicts.csv"
    with review_csv_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=[
                "bill_type",
                "bill_file",
                "extracted_customer",
                "extracted_amount",
                "best_score",
                "candidate_sales_rows",
                "reason",
            ],
        )
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


def build_sheet_write_plan(
    accepted_assignments: list[Assignment],
    insurance_col: int,
    rto_col: int,
    max_row: int,
    clear_existing: bool,
) -> SheetWritePlan:
    value_updates = [
        CellValueUpdate(
            row_index=assignment.row_index,
            col_index=insurance_col if assignment.bill_type == "insurance" else rto_col,
            value=float(assignment.amount),
        )
        for assignment in accepted_assignments
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


def run_processing_for_sheet(
    header_row: list[str],
    data_rows: list[list[str]],
    insurance_paths: list[Path],
    rto_paths: list[Path],
    output_dir: Path,
    config: ProcessingConfig,
    sheet_reference: str,
    sheet_title: str,
) -> tuple[ProcessingResult, SheetWritePlan]:
    customer_col, insurance_col, rto_col = find_header_indices(
        header_row=header_row,
        customer_header=config.customer_header,
        insurance_header=config.insurance_header,
        rto_header=config.rto_header,
    )

    sales_rows, max_row = build_sales_rows(data_rows, customer_col=customer_col)
    if not sales_rows:
        raise ValueError("No sales rows found with customer values.")

    bills = [("insurance", path) for path in insurance_paths] + [("rto", path) for path in rto_paths]
    review_rows: list[ReviewRow] = []
    assignments: list[Assignment] = []

    parse_failures = 0
    no_match = 0
    multi_match = 0
    row_conflicts = 0

    for bill_type, path in bills:
        try:
            text = extract_text(path)
        except Exception as exc:  # pragma: no cover - runtime issue
            parse_failures += 1
            review_rows.append(
                ReviewRow(
                    bill_type=bill_type,
                    bill_file=path.name,
                    extracted_customer="",
                    extracted_amount="",
                    best_score="",
                    candidate_sales_rows="",
                    reason=f"TEXT_EXTRACTION_ERROR: {exc}",
                )
            )
            continue

        extracted_customer, customer_error = extract_customer(text, config.customer_labels)
        amount, amount_error = extract_final_amount(text, config.amount_labels, config.amount_position)

        if customer_error or amount_error:
            parse_failures += 1
            review_rows.append(
                ReviewRow(
                    bill_type=bill_type,
                    bill_file=path.name,
                    extracted_customer=extracted_customer or "",
                    extracted_amount=str(amount) if amount is not None else "",
                    best_score="",
                    candidate_sales_rows="",
                    reason="; ".join(
                        item for item in [customer_error, amount_error] if item is not None
                    ),
                )
            )
            continue

        assert extracted_customer is not None
        assert amount is not None

        scored_rows = score_sales_rows(
            extracted_customer=extracted_customer,
            sales_rows=sales_rows,
        )
        candidates = [
            item for item in scored_rows
            if item[1] >= config.name_threshold
        ]

        if not candidates:
            # Safe fallback: if one clearly best candidate exists, accept it.
            if scored_rows and scored_rows[0][1] >= 80:
                top_row, top_score = scored_rows[0]
                second_score = scored_rows[1][1] if len(scored_rows) > 1 else 0.0
                if top_score - second_score >= 10:
                    assignments.append(
                        Assignment(
                            bill_type=bill_type,
                            bill_file=path.name,
                            row_index=top_row.row_index,
                            amount=amount,
                            matched_customer=top_row.customer_raw,
                            score=top_score,
                        )
                    )
                    continue

            no_match += 1
            review_rows.append(
                ReviewRow(
                    bill_type=bill_type,
                    bill_file=path.name,
                    extracted_customer=extracted_customer,
                    extracted_amount=str(amount),
                    best_score=f"{scored_rows[0][1]:.2f}" if scored_rows else "",
                    candidate_sales_rows=serialize_candidates(scored_rows[:3]) if scored_rows else "",
                    reason="NO_MATCH",
                )
            )
            continue

        if len(candidates) > 1:
            multi_match += 1
            review_rows.append(
                ReviewRow(
                    bill_type=bill_type,
                    bill_file=path.name,
                    extracted_customer=extracted_customer,
                    extracted_amount=str(amount),
                    best_score=f"{candidates[0][1]:.2f}",
                    candidate_sales_rows=serialize_candidates(candidates),
                    reason="MULTIPLE_SALES_ROWS",
                )
            )
            continue

        selected_row, score = candidates[0]
        assignments.append(
            Assignment(
                bill_type=bill_type,
                bill_file=path.name,
                row_index=selected_row.row_index,
                amount=amount,
                matched_customer=selected_row.customer_raw,
                score=score,
            )
        )

    by_row_and_type: dict[tuple[int, str], list[Assignment]] = {}
    for assignment in assignments:
        key = (assignment.row_index, assignment.bill_type)
        by_row_and_type.setdefault(key, []).append(assignment)

    accepted_assignments: list[Assignment] = []
    for key, values in by_row_and_type.items():
        if len(values) == 1:
            accepted_assignments.append(values[0])
            continue

        row_conflicts += len(values)
        row_idx, bill_type = key
        review_rows.append(
            ReviewRow(
                bill_type=bill_type,
                bill_file=", ".join(item.bill_file for item in values),
                extracted_customer=values[0].matched_customer,
                extracted_amount=", ".join(str(item.amount) for item in values),
                best_score=", ".join(f"{item.score:.2f}" for item in values),
                candidate_sales_rows=f"row={row_idx}",
                reason="MULTIPLE_BILLS_FOR_ROW_TYPE",
            )
        )

    review_csv_path = write_review_csv(output_dir=output_dir, review_rows=review_rows)
    rows_updated = len({item.row_index for item in accepted_assignments})
    write_plan = build_sheet_write_plan(
        accepted_assignments=accepted_assignments,
        insurance_col=insurance_col,
        rto_col=rto_col,
        max_row=max_row,
        clear_existing=config.clear_existing,
    )

    result = ProcessingResult(
        review_csv_path=review_csv_path,
        bills_processed=len(bills),
        bills_updated=len(accepted_assignments),
        rows_updated=rows_updated,
        bills_review=len(review_rows),
        parse_failures=parse_failures,
        no_match=no_match,
        multi_match=multi_match,
        row_conflicts=row_conflicts,
        sheet_reference=sheet_reference,
        sheet_title=sheet_title,
    )
    return result, write_plan

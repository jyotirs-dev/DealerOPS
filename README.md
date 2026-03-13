# Insurance + RTO Sales Updater

A modular web application that updates a Google Sheet with Insurance and RTO bill amounts extracted from uploaded PDF/image bills.

## Architecture

The application follows a **functional-programming-oriented** design with clear separation of concerns:

```
insurance_rto_updater/           # Core package
├── models.py                    # All data classes (pure data containers)
├── extraction/                  # Data extraction layer (no business logic)
│   ├── ocr.py                   # Tesseract OCR engine (CLI + pytesseract)
│   ├── pdf.py                   # PDF text extraction (PyMuPDF + sips fallback)
│   ├── text_parser.py           # Parse customer name + amount from bill text
│   └── file_router.py           # Route file → extractor by extension
├── domain/                      # Insurance + RTO business rules
│   ├── normalization.py         # Text normalization utilities
│   ├── matching.py              # Fuzzy name scoring and candidate selection
│   └── assignment.py            # Bill → sheet-row assignment + conflict detection
├── validation/                  # Comparison and validation helpers
│   └── comparator.py            # Header lookup, sales-row building, write-plan
├── integrations/                # External service adapters
│   └── google_sheets.py         # Google Sheets read/write (gspread)
├── orchestration/               # Pipeline wiring
│   └── pipeline.py              # extract → match → assign → upload
└── output/                      # Artifact writers
    └── csv_writer.py            # Review CSV generation

app.py                           # Flask web app (thin HTTP layer only)
processor.py                     # Backward-compat shim (→ new package)
sheets_adapter.py                # Backward-compat shim (→ new package)
```

### Design Principles

- **Pure functions** — most functions are data-in → data-out with no side effects.
- **No shared mutable state** — each function receives its inputs explicitly.
- **Composition over classes** — small functions composed in the pipeline.
- **Single responsibility** — each module does one thing well.
- **Documented business logic** — insurance/RTO rules are explained in docstrings.

## Features

- Paste a Google Sheet URL and upload multiple insurance/RTO bills.
- Extract bill text from PDFs and images via OCR.
- Extract final amount using **label + position** rule.
- Match bills to sales rows using **fuzzy customer name matching** (threshold configurable).
- Write matched amounts to the Insurance/RTO columns.
- Generate conflict report CSV for unmatched or ambiguous cases.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### OCR Requirement

For image/scanned documents, install Tesseract:

- macOS (Homebrew): `brew install tesseract`

Text PDFs work without Tesseract. Image OCR will fail gracefully (bills go to review CSV).

### PDF Extraction

- **Preferred**: PyMuPDF extracts text natively from PDFs.
- **Fallback (macOS)**: `sips + tesseract` OCR when PyMuPDF is unavailable.

## Google Sheets Setup

1. Create a Google Cloud service account and download the JSON key file.
2. Set the environment variable:
   ```bash
   export GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/to/service-account.json"
   ```
3. Share your target Google Sheet with the service account email as **Editor**.

## Run

```bash
python3 app.py
```

Open: `http://127.0.0.1:5001`

## Tests

```bash
python3 -m pytest tests/ -v
```

### Test Structure

| Test file | What it covers |
|---|---|
| `test_domain.py` | Normalization, fuzzy matching, assignment logic |
| `test_extraction.py` | Customer + amount parsing from bill text |
| `test_validation.py` | Header mapping, sales-row building, write plans |
| `test_processor_sheet.py` | End-to-end pipeline (mocked OCR) |
| `test_sheets_adapter.py` | Google Sheets adapter (fake gspread) |

## Form Inputs

- **Google Sheet URL**: Full spreadsheet URL.
- **Worksheet Name** (optional): Tab name; blank = first worksheet.
- **Customer Column Header**: Header containing customer names.
- **Insurance / RTO Column Headers**: Columns to overwrite.
- **Customer Labels**: Bill text labels near the customer name.
- **Final Amount Labels**: Bill text labels near the payable amount.
- **Amount Position**: `same_line` or `next_line` relative to label.
- **Name Match Threshold**: Fuzzy similarity (0–100, recommended: 95).

## Outputs

- In-place updates on the target Google Sheet.
- `review_conflicts.csv` for cases needing manual review:
  - Parse failures
  - No customer match
  - Multiple sales-row matches
  - Multiple bills for same row and bill type

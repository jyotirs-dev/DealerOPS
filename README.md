# Insurance + RTO Sales Updater (Web App)

This app updates a Google Sheet with Insurance and RTO bill amounts from uploaded PDF/image bills.

## Features

- Paste a Google Sheet URL and upload multiple insurance/RTO bills.
- Extract bill text from PDFs and images.
- Extract final amount using **label + fixed position** rule.
- Match bills to sales rows using **customer name only** (fuzzy threshold configurable).
- Overwrite existing Insurance/RTO columns in the same worksheet.
- Generate conflict report CSV for unmatched or ambiguous cases.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The app uses Google client libraries + `gspread` for Sheets API access via service account.

### OCR requirement

For image/scanned documents, install Tesseract on your machine:

- macOS (Homebrew): `brew install tesseract`

If Tesseract is missing, text PDFs still work, but image OCR may fail and those bills will go to review CSV.

### PDF fallback behavior

- Preferred path: `PyMuPDF` extracts text directly from PDFs.
- Fallback path (macOS): if `PyMuPDF` is unavailable, the app uses `sips + tesseract` OCR to process PDFs.
- Accuracy is usually better with direct PDF text extraction than OCR fallback.

## Google Sheets setup

1. Create a Google Cloud service account and download the JSON key file.
2. Set environment variable:
   ```bash
   export GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/to/service-account.json"
   ```
3. Share your target Google Sheet with the service account email as **Editor**.
4. In the app UI, paste full Google Sheet URL, for example:
   `https://docs.google.com/spreadsheets/d/<spreadsheet_id>/edit`

## Run

```bash
python3 app.py
```

Open: `http://127.0.0.1:5000`

## Form Inputs

- `Google Sheet URL`: full URL of spreadsheet to update.
- `Worksheet Name` (optional): tab name; if blank, first worksheet is used.
- `Customer Column Header`: header in sales sheet containing customer names.
- `Insurance Column Header`: existing insurance column to overwrite.
- `RTO Column Header`: existing RTO column to overwrite.
- `Customer Labels`: bill text labels used to locate customer name.
- `Final Amount Labels`: bill text labels used to locate final payable amount.
- `Amount Position`:
  - `same_line`: amount appears on same line as label.
  - `next_line`: amount appears on the next line after label.
- `Name Match Threshold`: fuzzy similarity score from `0` to `100` (recommended `95`).

## Outputs

- In-place updates on target Google Sheet.
- `review_conflicts.csv`: cases that need manual review:
  - parse issues
  - no customer match
  - multiple sales-row matches
  - multiple bills for same row and bill type

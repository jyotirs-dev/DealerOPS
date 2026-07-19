# Insurance + RTO Workbook Updater

This repository contains a Flask + React application for two Excel-based dealership workflows:

1. Update a vehicle sales workbook by extracting Insurance and RTO amounts from uploaded bills.
2. Generate a formatted Vehicle Sales Register workbook from a raw invoice export.

The current web app is workbook-first. It reads and writes local Excel files and returns downloadable outputs. A Google Sheets adapter still exists in the repository as legacy integration code, but the live HTTP flow uses local workbooks.

## Current Product Surface

### 1. Workbook Updater

Upload:

- One sales workbook (`.xlsx` or `.xlsm`)
- Zero or more insurance bills (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp`)
- Zero or more RTO bills (same formats)

The app will:

- Find the first worksheet containing the required headers:
  - `Contact Name`
  - `Insurance`
  - `(RTO+ Agent fee 500)`
- Extract customer names and payable amounts from the uploaded bills
- Match each bill to the correct sales row using fuzzy name matching
- Write the accepted values back into a workbook copy
- Produce `review_conflicts.csv` for anything that could not be verified automatically

### 2. Sales Register Generator

Upload:

- One raw OEM / DMS invoice export workbook

The app will:

- Filter the raw data down to invoiced rows
- Build a formatted `Vehicle Sales Register` worksheet
- Pre-fill known columns from the export
- Insert formula-driven columns
- Leave manual-entry columns blank for dealership staff

## Architecture

The application is split into a thin HTTP/UI layer and a domain-focused processing package:

```text
app.py
frontend/
insurance_rto_updater/
tests/
```

### Backend layers

```text
insurance_rto_updater/
├── models.py
├── extraction/
│   ├── file_router.py
│   ├── ocr.py
│   ├── pdf.py
│   └── text_parser.py
├── domain/
│   ├── amounts.py
│   ├── assignment.py
│   ├── matching.py
│   └── normalization.py
├── validation/
│   └── comparator.py
├── integrations/
│   ├── local_workbook.py
│   └── google_sheets.py
├── orchestration/
│   └── pipeline.py
└── output/
    ├── csv_writer.py
    └── sales_register.py
```

### Frontend layers

```text
frontend/src/
├── App.tsx
├── main.tsx
├── styles.css
└── lib/
    └── workbook.ts
```

## Request Flow

### Workbook updater flow

1. The React app reads the uploaded workbook locally for preview and validates the fixed headers.
2. The browser posts the workbook and bill files to `POST /api/process`.
3. Flask saves the uploads into a per-job directory.
4. `LocalWorkbookAdapter` loads the target worksheet and exposes header/data rows to the pipeline.
5. The orchestration pipeline:
   - extracts text from PDFs or images
   - parses customer names and amounts
   - adjusts amounts by bill type
   - matches bills to worksheet rows
   - detects conflicts and preserved existing values
   - builds a write plan
   - writes a review CSV
6. Flask applies the write plan to the workbook copy and returns:
   - summary metrics
   - preview data
   - download URL for the updated workbook
   - download URL for `review_conflicts.csv`

### Sales register flow

1. The React app posts a raw invoice workbook to `POST /api/generate-sales-register`.
2. Flask saves the upload into a per-job directory.
3. `generate_sales_register()` reads the first worksheet with pandas.
4. The generator writes a new styled workbook with formulas and manual-entry columns.
5. Flask returns the download URL and generation summary.

## Backend Walkthrough

### `app.py`

`app.py` is intentionally thin:

- Serves the built React app from `frontend/dist`
- Exposes:
  - `POST /api/process`
  - `POST /api/generate-sales-register`
  - `GET /download/<job_id>/<filename>`
  - `GET /api/health`
- Validates form inputs and file extensions
- Creates per-job upload/output folders
- Delegates business logic to `insurance_rto_updater`

### `integrations/local_workbook.py`

This is the active workbook adapter used by the web app.

Responsibilities:

- Open `.xlsx` / `.xlsm` files with `openpyxl`
- Find the first worksheet containing the fixed headers
- Convert worksheet data into normalized `SheetData`
- Apply `SheetWritePlan` updates back into the workbook
- Return workbook previews for API responses

### `orchestration/pipeline.py`

This is the main coordinator for bill processing.

High-level steps:

1. Resolve workbook header indices
2. Build normalized `SalesRow` records
3. Extract and parse every uploaded bill
4. Match parsed bills to rows
5. Detect duplicate row/type conflicts
6. Preserve existing cell values when `clear_existing` is off
7. Build the final write plan
8. Write the review CSV
9. Return `ProcessingResult`

This module deliberately keeps decisions delegated to lower layers.

### `extraction/`

This layer reads unstructured documents and produces structured parse inputs.

- `file_router.py`
  - Routes `.pdf` files through the PDF extractor
  - Routes all supported image formats through OCR
- `pdf.py`
  - Uses PyMuPDF first for native text
  - Falls back to OCR per page when needed
  - Falls back further to `sips + tesseract` on macOS if PyMuPDF is unavailable
- `ocr.py`
  - Preprocesses images before OCR
  - Uses `pytesseract` when available
  - Falls back to the `tesseract` CLI
- `text_parser.py`
  - Fuzzy-matches customer labels and amount labels
  - Filters false customer-name candidates
  - Extracts Indian-format currency values
  - Handles special insurance MIS report parsing
  - Handles pay-in-slip extraction paths

### `domain/`

This layer contains the business rules.

- `normalization.py`
  - Normalizes names and free text before comparison
- `matching.py`
  - Scores an extracted customer name against every sales-row customer
  - Uses `rapidfuzz` when installed, otherwise `SequenceMatcher`
  - Adds token-overlap heuristics to avoid weak fuzzy matches
- `assignment.py`
  - Accepts exactly one strong match
  - Sends ambiguous cases to review
  - Applies a safe-fallback heuristic when the best score is strong and clearly ahead
  - Supports filename-based first-name fallback when customer labels are missing
  - Detects multiple bills targeting the same row and bill type
- `amounts.py`
  - Adds the fixed `₹500` agent fee to RTO bill amounts before writing

### `validation/comparator.py`

Despite the name, this module is really the deterministic workbook-write planner.

Responsibilities:

- Map header names to column indices
- Convert raw rows into `SalesRow` objects
- Prevent overwriting existing Insurance / RTO values when `clear_existing` is off
- Produce the final `SheetWritePlan`

### `output/`

- `csv_writer.py`
  - Writes the review/conflict CSV consumed by the UI
- `sales_register.py`
  - Generates the formatted Vehicle Sales Register workbook
  - Applies styles, formulas, widths, and manual-entry columns

## Frontend Walkthrough

### `frontend/src/App.tsx`

This file currently owns nearly all UI behavior.

It manages two app modes:

- `updater`
- `sales-register`

#### Workbook updater UI

The updater mode is organized around three tabs:

- `Sales Sheet`
- `RTO Receipts`
- `Insurance Files`

Key responsibilities:

- Track workbook upload state
- Track insurance and RTO file lists independently
- Hold advanced parser settings:
  - customer labels
  - amount labels
  - amount position
  - name threshold
  - clear existing
- Submit `FormData` to `/api/process`
- Refresh the workbook preview from the returned download URL
- Toggle between worksheet preview and review-row preview
- Render summary cards and download links

#### Sales register UI

The sales-register mode:

- Uploads a raw invoice workbook
- Calls `/api/generate-sales-register`
- Displays rows written and detected month/year
- Lists manual-entry columns the user must still fill
- Downloads and previews the generated workbook

### `frontend/src/lib/workbook.ts`

This module is important because it makes the UI feel immediate before any server call.

Responsibilities:

- Read uploaded workbooks in the browser with `xlsx`
- Evaluate formulas with `hyperformula` when possible
- Normalize header names
- Find the worksheet containing the required fixed headers
- Convert the worksheet into a grid-friendly preview model

This same preview helper is reused after downloads so the UI can show the updated or generated workbook without waiting for a manual reload.

### `frontend/src/main.tsx`

This is the React bootstrap:

- registers AG Grid community modules
- mounts the app into `#root`

### `frontend/src/styles.css`

The UI is custom styled instead of using a component library.

Notable choices:

- warm paper-like background
- glassmorphism-style panels
- AG Grid for workbook preview
- a mode switcher plus tabbed upload flow

## Setup

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## OCR and PDF Requirements

### Tesseract

Scanned/image bills require Tesseract.

macOS:

```bash
brew install tesseract
```

If Tesseract is missing, OCR-based uploads will fail into review rows instead of silently producing bad matches.

### PyMuPDF

PyMuPDF is the preferred PDF extractor and is already listed in `requirements.txt`.

Behavior:

- text PDFs: use native extraction when possible
- scanned PDFs: render pages and OCR them
- fallback on macOS without PyMuPDF: `sips + tesseract`

## Running the App

### Option 1: Flask serves the built frontend

Build the frontend first:

```bash
cd frontend
npm run build
cd ..
python3 app.py
```

Open:

```text
http://127.0.0.1:5001
```

### Option 2: Split frontend/backend development

Terminal 1:

```bash
python3 app.py
```

Terminal 2:

```bash
cd frontend
npm run dev
```

The Vite dev server proxies `/api` and `/download` to `http://127.0.0.1:5001`.

## Tests

### Backend tests

```bash
python3 -m pytest tests -q
```

Covered areas:

- API workflow
- workbook adapter
- extraction rules
- domain matching and assignment rules
- write-plan generation
- sales register generation

### Frontend tests

```bash
cd frontend
npm run test
```

## Notable Business Rules

- The active workbook worksheet is identified by the fixed headers, not by a hard-coded sheet name.
- Customer matching is fuzzy and threshold-based.
- When no candidate clears the threshold, the app can still accept a safe fallback if the best score is strong and clearly ahead of the runner-up.
- RTO amounts get `₹500` added before writing.
- When `clear_existing` is off, existing Insurance / RTO cell values are preserved and the skipped updates are sent to review instead.
- Some insurance uploads can expand into multiple parsed entries, such as MIS reports.

## Repository Notes

- `integrations/google_sheets.py` is present but not part of the current HTTP workflow.
- `codebase_walkthrough.md` documents the older Google Sheets-centric shape of the project and may lag behind the live implementation.
- The tests reflect the current workbook-first behavior more accurately than the old narrative docs.

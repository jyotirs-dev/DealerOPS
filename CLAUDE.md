# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Flask + React application with two Excel-based dealership workflows: (1) matching insurance/RTO bill uploads to rows in a sales workbook via OCR/fuzzy matching, and (2) generating a formatted Vehicle Sales Register workbook from a raw invoice export.

## Commands

### Run the app

```bash
./launch.sh            # dev mode: Flask on :5001 + Vite on :5173 (hot reload), auto-installs deps
./launch.sh --prod      # builds frontend, serves everything from Flask on :5001
```

Manual equivalent:

```bash
python3 app.py                    # backend only, http://127.0.0.1:5001
cd frontend && npm run dev        # frontend only, http://localhost:5173 (proxies /api, /download to :5001)
```

### Backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest tests -q                          # all tests
python3 -m pytest tests/test_domain.py -q           # single file
python3 -m pytest tests/test_domain.py::test_name -q  # single test
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # Vite dev server
npm run build      # tsc -b && vite build (type-checks, then builds to frontend/dist)
npm run test       # vitest run
npm run preview    # preview a production build
```

There is no configured lint command (no ESLint/Prettier config, no Python linter) — `npm run build`'s `tsc -b` step is the only type-checking gate.

### External requirements

OCR/PDF extraction needs Tesseract installed on the host (`brew install tesseract` on macOS). PyMuPDF (in requirements.txt) is the preferred PDF text extractor; missing Tesseract causes OCR uploads to fail into review rows rather than silently producing bad matches.

## Architecture

The backend is a thin HTTP layer (`app.py`) over a layered domain package (`insurance_rto_updater/`); the frontend does client-side preview work before ever hitting the server.

```
app.py                          # Flask routes, upload handling, per-job folders — no business logic
insurance_rto_updater/
├── models.py                   # shared dataclasses (SalesRow, SheetData, SheetWritePlan, ProcessingResult, ...)
├── extraction/                 # unstructured input -> structured parse candidates
│   ├── file_router.py          #   routes .pdf vs image files to the right extractor
│   ├── pdf.py                  #   PyMuPDF native text -> OCR-per-page fallback -> sips+tesseract (macOS)
│   ├── ocr.py                  #   image preprocessing + pytesseract, falls back to tesseract CLI
│   └── text_parser.py          #   fuzzy label matching for names/amounts, currency parsing, MIS/pay-in-slip formats
├── domain/                     # business rules, no I/O
│   ├── normalization.py        #   name/text normalization used before any comparison
│   ├── matching.py             #   fuzzy score of parsed name vs. every sales row (rapidfuzz, else SequenceMatcher)
│   ├── assignment.py           #   accepts one strong match, sends ambiguous cases to review, dup detection
│   └── amounts.py              #   RTO bills get a fixed ₹500 agent fee added before writing
├── validation/comparator.py    # maps headers -> column indices, builds SheetWritePlan, preserves existing cells
├── integrations/
│   ├── local_workbook.py       #   ACTIVE adapter: openpyxl read/write of .xlsx/.xlsm via fixed-header lookup
│   └── google_sheets.py        #   legacy, not wired into any live HTTP route — do not assume it runs
├── orchestration/pipeline.py   # coordinates extraction -> matching -> conflict detection -> write plan -> review CSV
└── output/
    ├── csv_writer.py           #   writes review_conflicts.csv
    └── sales_register.py       #   generates the styled Vehicle Sales Register workbook

frontend/src/
├── App.tsx                     # owns nearly all UI state/behavior for both app modes (updater, sales-register)
├── main.tsx                    # React bootstrap, registers AG Grid community modules
├── lib/workbook.ts             # client-side xlsx parsing + hyperformula evaluation for instant preview
└── components/                 # extracted UI pieces used by App.tsx
```

### Request flows

**Workbook updater** (`POST /api/process`): browser validates headers and previews the workbook locally first → Flask saves uploads to a per-job directory → `LocalWorkbookAdapter` loads the worksheet identified by fixed headers (`Contact Name`, `Insurance`, `(RTO+ Agent fee 500)`) → `orchestration/pipeline.py` extracts text, parses amounts, adjusts for bill type, matches bills to rows, detects conflicts, preserves existing values when `clear_existing` is off, builds a `SheetWritePlan`, writes `review_conflicts.csv` → Flask applies the plan to a workbook copy and returns summary + preview + download URLs.

**Sales register** (`POST /api/generate-sales-register`): Flask saves the raw invoice export → `generate_sales_register()` reads it with pandas, filters to invoiced rows, writes a new styled workbook with formulas and manual-entry columns left blank → Flask returns the download URL and a summary.

The active worksheet is always located by scanning for its fixed header row, never by a hard-coded sheet name/index — this is load-bearing for both flows.

## Code style & conventions

- **Python**: dataclasses (in `models.py`) as the shared vocabulary between layers — extend these rather than passing loose dicts/tuples across module boundaries. `domain/` modules are pure business logic with no file/network I/O; I/O lives in `extraction/`, `integrations/`, and `output/`. New parsing/matching rules belong in `domain/` or `extraction/text_parser.py`, not in `orchestration/pipeline.py` or `app.py`.
- **Frontend**: TypeScript with React function components. `lib/workbook.ts` is the sole place that touches `xlsx`/`hyperformula` parsing — reuse it for any new preview logic instead of re-parsing workbooks elsewhere. UI composition lives in `components/`; avoid growing `App.tsx` further where a piece can be extracted.
- Match existing formatting in the file you're editing (no enforced linter/formatter in either stack).

## Hard constraint

When refactoring existing code, the observable public API and functional behavior must be preserved exactly: same function/endpoint signatures, same request/response shapes, same file outputs (workbook contents, `review_conflicts.csv` format), and same matching/assignment/amount-calculation outcomes. Verify with the existing test suite (`pytest tests -q`, `npm run test`) before and after — a refactor that changes test results is a regression, not a refactor.

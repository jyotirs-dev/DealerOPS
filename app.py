"""
app.py – Flask web application (thin HTTP layer)
=================================================
This module handles *only* HTTP concerns:
  - Request parsing and validation.
  - File upload management.
  - Rendering templates and serving downloads.

All business logic is delegated to the ``insurance_rto_updater`` package.
"""
from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from insurance_rto_updater.integrations.google_sheets import GoogleSheetsAdapter
from insurance_rto_updater.models import ProcessingConfig
from insurance_rto_updater.orchestration.pipeline import run_processing_pipeline

# ---------------------------------------------------------------------------
# Application constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / "uploads"
OUTPUT_ROOT = BASE_DIR / "outputs"
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"
}


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    """Create upload and output directories if they don't exist."""
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def _save_uploaded_files(
    files: list[Any],
    target_dir: Path,
) -> list[Path]:
    """
    Persist uploaded file-storage objects to disk.

    Returns a list of saved file paths.
    Raises ``ValueError`` for unsupported file types.
    """
    saved: list[Path] = []
    target_dir.mkdir(parents=True, exist_ok=True)

    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        safe_name = secure_filename(file_storage.filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {safe_name}")
        destination = target_dir / safe_name
        file_storage.save(destination)
        saved.append(destination)

    return saved


def _parse_csv_preview(
    csv_path: Path,
    max_rows: int = 30,
) -> list[dict[str, str]]:
    """Read the first *max_rows* of a CSV file for the results template."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []

    rows: list[dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append(row)
    return rows


def _parse_form_config() -> tuple[str, ProcessingConfig, str | None]:
    """
    Validate and extract all processing parameters from the submitted form.

    Returns ``(sheet_url, config, sheet_name)``.
    Raises ``ValueError`` for any missing or invalid input.
    """
    sheet_url = request.form.get("sheet_url", "").strip()
    if not sheet_url:
        raise ValueError("Google Sheet URL is required.")

    customer_col = request.form.get("customer_col", "").strip()
    insurance_col = request.form.get("insurance_col", "").strip()
    rto_col = request.form.get("rto_col", "").strip()
    if not customer_col or not insurance_col or not rto_col:
        raise ValueError(
            "Customer, Insurance, and RTO column headers are required."
        )

    # Parse and validate the fuzzy-match threshold.
    threshold_raw = request.form.get("name_threshold", "95").strip()
    try:
        name_threshold = float(threshold_raw)
    except ValueError as exc:
        raise ValueError("Name threshold must be numeric.") from exc
    if name_threshold < 0 or name_threshold > 100:
        raise ValueError("Name threshold must be between 0 and 100.")

    # Parse comma-separated label lists.
    amount_labels = [
        item.strip()
        for item in request.form.get("amount_labels", "").split(",")
        if item.strip()
    ]
    customer_labels = [
        item.strip()
        for item in request.form.get("customer_labels", "").split(",")
        if item.strip()
    ]
    if not amount_labels:
        raise ValueError("Provide at least one final amount label.")
    if not customer_labels:
        raise ValueError("Provide at least one customer label.")

    amount_position = request.form.get("amount_position", "same_line").strip()
    if amount_position not in {"same_line", "next_line"}:
        raise ValueError(
            "Amount position must be either same_line or next_line."
        )

    clear_existing = request.form.get("clear_existing", "").strip() == "1"
    sheet_name = request.form.get("sheet_name", "").strip() or None

    config = ProcessingConfig(
        sheet_name=sheet_name,
        customer_header=customer_col,
        insurance_header=insurance_col,
        rto_header=rto_col,
        customer_labels=customer_labels,
        amount_labels=amount_labels,
        amount_position=amount_position,
        name_threshold=name_threshold,
        clear_existing=clear_existing,
    )

    return sheet_url, config, sheet_name


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = "local-dev-only"
_ensure_dirs()


@app.get("/")
def index() -> str:
    """Render the main upload form."""
    return render_template("index.html")


@app.post("/process")
def process_files() -> str:
    """
    Handle the bill-processing form submission.

    Workflow:
      1. Parse and validate form inputs.
      2. Save uploaded files to disk.
      3. Load sheet data via the Google Sheets adapter.
      4. Run the processing pipeline.
      5. Apply the write plan to the sheet.
      6. Render the results page.
    """
    try:
        sheet_url, config, sheet_name = _parse_form_config()

        insurance_uploads = request.files.getlist("insurance_files")
        rto_uploads = request.files.getlist("rto_files")
        if not insurance_uploads and not rto_uploads:
            raise ValueError("Upload at least one insurance or RTO bill.")

        # Create a unique job directory for this processing run.
        job_id = uuid.uuid4().hex
        upload_dir = UPLOAD_ROOT / job_id
        output_dir = OUTPUT_ROOT / job_id

        insurance_paths = _save_uploaded_files(
            insurance_uploads, upload_dir / "insurance"
        )
        rto_paths = _save_uploaded_files(
            rto_uploads, upload_dir / "rto"
        )

        # Load sheet data.
        service_account_file = os.environ.get(
            "GOOGLE_SERVICE_ACCOUNT_FILE", ""
        ).strip()
        if not service_account_file:
            raise ValueError(
                "Set GOOGLE_SERVICE_ACCOUNT_FILE to your "
                "service-account JSON path."
            )

        sheets_adapter = GoogleSheetsAdapter(
            sheet_url=sheet_url,
            sheet_name=sheet_name,
            credentials_file=Path(service_account_file),
        )
        sheet_data = sheets_adapter.load_sheet_data()

        # Run the processing pipeline.
        result, write_plan = run_processing_pipeline(
            header_row=sheet_data.header_row,
            data_rows=sheet_data.data_rows,
            insurance_paths=insurance_paths,
            rto_paths=rto_paths,
            output_dir=output_dir,
            config=config,
            sheet_reference=sheet_data.spreadsheet_url,
            sheet_title=sheet_data.sheet_title,
        )

        # Apply changes to the Google Sheet.
        sheets_adapter.apply_write_plan(
            sheet_title=sheet_data.sheet_title,
            write_plan=write_plan,
        )

        # Render results.
        preview_rows = _parse_csv_preview(result.review_csv_path)
        return render_template(
            "result.html",
            result=result,
            job_id=job_id,
            preview_rows=preview_rows,
            sheet_url=sheet_data.spreadsheet_url,
            sheet_title=sheet_data.sheet_title,
        )

    except Exception as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))


@app.get("/download/<job_id>/<filename>")
def download_file(job_id: str, filename: str):  # type: ignore[no-untyped-def]
    """Serve a generated file (e.g. review CSV) for download."""
    safe_filename = Path(filename).name
    target = OUTPUT_ROOT / job_id / safe_filename
    if not target.exists():
        abort(404)
    return send_file(target, as_attachment=True)


# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    port_raw = os.environ.get("PORT", "5001").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 5001
    debug = os.environ.get("FLASK_DEBUG", "1").strip() not in {
        "0", "false", "False"
    }
    app.run(host=host, port=port, debug=debug)

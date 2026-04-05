"""
app.py – Flask API + React SPA host
===================================
Serves the built React frontend and exposes the local-workbook processing API.
The core extraction and matching logic remains in ``insurance_rto_updater``.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from insurance_rto_updater.integrations.local_workbook import (
    FIXED_CUSTOMER_HEADER,
    FIXED_INSURANCE_HEADER,
    FIXED_RTO_HEADER,
    LocalWorkbookAdapter,
)
from insurance_rto_updater.models import ProcessingConfig, ProcessingResult
from insurance_rto_updater.orchestration.pipeline import run_processing_pipeline

# ---------------------------------------------------------------------------
# Application constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
UPLOAD_ROOT = BASE_DIR / "uploads"
OUTPUT_ROOT = BASE_DIR / "outputs"
WORKBOOK_EXTENSIONS = {".xlsx", ".xlsm"}
ALLOWED_BILL_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"
}
DEFAULT_CUSTOMER_LABELS = ["Insured", "Insured Name", "Received From"]
DEFAULT_AMOUNT_LABELS = [
    "Received with Thanks Rs",
    "Grand Total (in Rs)",
    "Grand Total",
    "Final Amount",
    "Amount Payable",
    "Net Payable",
]


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def _save_uploaded_files(
    files: list[Any],
    target_dir: Path,
    allowed_extensions: set[str],
) -> list[Path]:
    saved: list[Path] = []
    target_dir.mkdir(parents=True, exist_ok=True)

    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        safe_name = secure_filename(file_storage.filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in allowed_extensions:
            raise ValueError(f"Unsupported file type: {safe_name}")
        destination = target_dir / safe_name
        file_storage.save(destination)
        saved.append(destination)

    return saved


def _save_uploaded_workbook(file_storage: Any, target_dir: Path) -> Path:
    if not file_storage or not file_storage.filename:
        raise ValueError("Upload an Excel workbook before processing.")

    saved = _save_uploaded_files(
        [file_storage],
        target_dir=target_dir,
        allowed_extensions=WORKBOOK_EXTENSIONS,
    )
    if not saved:
        raise ValueError("Upload an Excel workbook before processing.")
    return saved[0]


def _parse_csv_labels(field_name: str, default: list[str]) -> list[str]:
    raw = request.form.get(field_name, "").strip()
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


def _parse_processing_config() -> ProcessingConfig:
    threshold_raw = request.form.get("name_threshold", "95").strip()
    try:
        name_threshold = float(threshold_raw)
    except ValueError as exc:
        raise ValueError("Name threshold must be numeric.") from exc
    if name_threshold < 0 or name_threshold > 100:
        raise ValueError("Name threshold must be between 0 and 100.")

    amount_position = request.form.get("amount_position", "same_line").strip()
    if amount_position not in {"same_line", "next_line"}:
        raise ValueError("Amount position must be either same_line or next_line.")

    return ProcessingConfig(
        sheet_name=None,
        customer_header=FIXED_CUSTOMER_HEADER,
        insurance_header=FIXED_INSURANCE_HEADER,
        rto_header=FIXED_RTO_HEADER,
        customer_labels=_parse_csv_labels(
            "customer_labels", DEFAULT_CUSTOMER_LABELS
        ),
        amount_labels=_parse_csv_labels(
            "amount_labels", DEFAULT_AMOUNT_LABELS
        ),
        amount_position=amount_position,
        name_threshold=name_threshold,
        clear_existing=request.form.get("clear_existing", "").strip() == "1",
    )


def _summary_payload(result: ProcessingResult) -> dict[str, Any]:
    return {
        "billsProcessed": result.bills_processed,
        "billsUpdated": result.bills_updated,
        "rowsUpdated": result.rows_updated,
        "billsReview": result.bills_review,
        "parseFailures": result.parse_failures,
        "noMatch": result.no_match,
        "multiMatch": result.multi_match,
        "rowConflicts": result.row_conflicts,
    }


def _frontend_index_response():
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return send_file(index_path)
    return (
        "<h1>Frontend build not found.</h1>"
        "<p>Run <code>npm install</code> and <code>npm run build</code> in "
        "<code>frontend/</code> to serve the React app.</p>",
        503,
        {"Content-Type": "text/html; charset=utf-8"},
    )


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
_ensure_dirs()


@app.get("/")
def index():  # type: ignore[no-untyped-def]
    return _frontend_index_response()


@app.get("/assets/<path:filename>")
def frontend_assets(filename: str):  # type: ignore[no-untyped-def]
    assets_dir = FRONTEND_DIST / "assets"
    if not assets_dir.exists():
        abort(404)
    return send_from_directory(assets_dir, filename)


@app.get("/<path:path>")
def spa_fallback(path: str):  # type: ignore[no-untyped-def]
    if path.startswith("api/") or path.startswith("download/"):
        abort(404)
    return _frontend_index_response()


@app.post("/api/process")
def process_files():  # type: ignore[no-untyped-def]
    try:
        config = _parse_processing_config()

        workbook_upload = request.files.get("workbook")
        insurance_uploads = request.files.getlist("insurance_files[]")
        if not insurance_uploads:
            insurance_uploads = request.files.getlist("insurance_files")
        rto_uploads = request.files.getlist("rto_files[]")
        if not rto_uploads:
            rto_uploads = request.files.getlist("rto_files")

        if not insurance_uploads and not rto_uploads:
            raise ValueError("Upload at least one insurance or RTO bill.")

        job_id = uuid.uuid4().hex
        upload_dir = UPLOAD_ROOT / job_id
        output_dir = OUTPUT_ROOT / job_id

        workbook_path = _save_uploaded_workbook(
            workbook_upload,
            upload_dir / "workbook",
        )
        insurance_paths = _save_uploaded_files(
            insurance_uploads,
            upload_dir / "insurance",
            ALLOWED_BILL_EXTENSIONS,
        )
        rto_paths = _save_uploaded_files(
            rto_uploads,
            upload_dir / "rto",
            ALLOWED_BILL_EXTENSIONS,
        )

        workbook_adapter = LocalWorkbookAdapter(workbook_path)
        sheet_data = workbook_adapter.load_sheet_data()

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

        workbook_adapter.apply_write_plan(
            sheet_title=sheet_data.sheet_title,
            write_plan=write_plan,
        )

        updated_workbook_name = (
            f"{workbook_path.stem}_updated{workbook_path.suffix.lower()}"
        )
        workbook_adapter.save_copy(output_dir / updated_workbook_name)
        header_row, rows = workbook_adapter.sheet_preview(sheet_data.sheet_title)

        response_payload = {
            "jobId": job_id,
            "sheetTitle": sheet_data.sheet_title,
            "headerRow": header_row,
            "rows": rows,
            "summary": _summary_payload(result),
            "downloadUrl": f"/download/{job_id}/{updated_workbook_name}",
            "reviewCsvUrl": (
                f"/download/{job_id}/{result.review_csv_path.name}"
            ),
            "settings": {
                "customerHeader": FIXED_CUSTOMER_HEADER,
                "insuranceHeader": FIXED_INSURANCE_HEADER,
                "rtoHeader": FIXED_RTO_HEADER,
            },
        }
        return jsonify(response_payload)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Unexpected server error: {exc}"}), 500


@app.get("/download/<job_id>/<filename>")
def download_file(job_id: str, filename: str):  # type: ignore[no-untyped-def]
    safe_filename = Path(filename).name
    target = OUTPUT_ROOT / job_id / safe_filename
    if not target.exists():
        abort(404)
    return send_file(target, as_attachment=True)


@app.get("/api/health")
def healthcheck():  # type: ignore[no-untyped-def]
    return jsonify({"status": "ok"})


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

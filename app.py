from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from processor import ProcessingConfig, run_processing_for_sheet
from sheets_adapter import GoogleSheetsAdapter


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / "uploads"
OUTPUT_ROOT = BASE_DIR / "outputs"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def ensure_dirs() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def save_uploaded_files(files: list[Any], target_dir: Path) -> list[Path]:
    saved_paths: list[Path] = []
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
        saved_paths.append(destination)

    return saved_paths


def parse_csv_preview(csv_path: Path, max_rows: int = 30) -> list[dict[str, str]]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []

    rows: list[dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append(row)
    return rows


app = Flask(__name__)
app.config["SECRET_KEY"] = "local-dev-only"
ensure_dirs()


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/process")
def process_files() -> str:
    try:
        sheet_url = request.form.get("sheet_url", "").strip()
        if not sheet_url:
            raise ValueError("Google Sheet URL is required.")

        insurance_uploads = request.files.getlist("insurance_files")
        rto_uploads = request.files.getlist("rto_files")
        if not insurance_uploads and not rto_uploads:
            raise ValueError("Upload at least one insurance or RTO bill.")

        customer_col = request.form.get("customer_col", "").strip()
        insurance_col = request.form.get("insurance_col", "").strip()
        rto_col = request.form.get("rto_col", "").strip()
        if not customer_col or not insurance_col or not rto_col:
            raise ValueError("Customer, Insurance, and RTO column headers are required.")

        threshold_raw = request.form.get("name_threshold", "95").strip()
        try:
            name_threshold = float(threshold_raw)
        except ValueError as exc:
            raise ValueError("Name threshold must be numeric.") from exc
        if name_threshold < 0 or name_threshold > 100:
            raise ValueError("Name threshold must be between 0 and 100.")

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
            raise ValueError("Amount position must be either same_line or next_line.")
        clear_existing = request.form.get("clear_existing", "").strip() == "1"

        sheet_name = request.form.get("sheet_name", "").strip() or None

        job_id = uuid.uuid4().hex
        upload_dir = UPLOAD_ROOT / job_id
        insurance_dir = upload_dir / "insurance"
        rto_dir = upload_dir / "rto"
        output_dir = OUTPUT_ROOT / job_id

        insurance_paths = save_uploaded_files(insurance_uploads, insurance_dir)
        rto_paths = save_uploaded_files(rto_uploads, rto_dir)

        service_account_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not service_account_file:
            raise ValueError("Set GOOGLE_SERVICE_ACCOUNT_FILE to your service-account JSON path.")

        sheets_adapter = GoogleSheetsAdapter(
            sheet_url=sheet_url,
            sheet_name=sheet_name,
            credentials_file=Path(service_account_file),
        )
        sheet_data = sheets_adapter.load_sheet_data()

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

        result, write_plan = run_processing_for_sheet(
            header_row=sheet_data.header_row,
            data_rows=sheet_data.data_rows,
            insurance_paths=insurance_paths,
            rto_paths=rto_paths,
            output_dir=output_dir,
            config=config,
            sheet_reference=sheet_data.spreadsheet_url,
            sheet_title=sheet_data.sheet_title,
        )
        sheets_adapter.apply_write_plan(sheet_title=sheet_data.sheet_title, write_plan=write_plan)

        preview_rows = parse_csv_preview(result.review_csv_path)
        return render_template(
            "result.html",
            result=result,
            job_id=job_id,
            preview_rows=preview_rows,
            sheet_url=sheet_data.spreadsheet_url,
            sheet_title=sheet_data.sheet_title,
        )

    except Exception as exc:  # pragma: no cover - runtime surfaced in UI
        flash(str(exc), "error")
        return redirect(url_for("index"))


@app.get("/download/<job_id>/<filename>")
def download_file(job_id: str, filename: str):  # type: ignore[no-untyped-def]
    safe_filename = Path(filename).name
    target = OUTPUT_ROOT / job_id / safe_filename
    if not target.exists():
        abort(404)
    return send_file(target, as_attachment=True)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    port_raw = os.environ.get("PORT", "5000").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 5000
    debug = os.environ.get("FLASK_DEBUG", "1").strip() not in {"0", "false", "False"}
    app.run(host=host, port=port, debug=debug)

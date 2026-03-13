"""
pdf.py – PDF text extraction
============================
Two extraction paths, tried in order:

1. **PyMuPDF (``fitz``)** – Preferred.  Extracts native text first, then
   falls back to rendering each page as an image and running OCR.
2. **sips + Tesseract** – macOS-only fallback when PyMuPDF is not installed.
   Converts the first page to PNG via ``sips``, then OCRs the image.

Performance note:
  Native text extraction is *much* faster and more accurate than the OCR
  fallback.  Users should install PyMuPDF whenever possible.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from insurance_rto_updater.extraction.ocr import ocr_image

# PyMuPDF is optional — image-based OCR is the fallback.
try:
    import fitz
except ImportError:
    fitz = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# macOS sips fallback (used only when PyMuPDF is unavailable)
# ---------------------------------------------------------------------------

def _extract_pdf_text_with_sips(path: Path) -> str:
    """
    Convert a PDF to PNG using macOS ``sips`` and OCR the result.

    This is a last-resort path.  It only processes the *first page* and
    requires both ``sips`` (ships with macOS) and Tesseract.

    Raises ``RuntimeError`` if ``sips`` is missing or conversion fails.
    """
    if shutil.which("sips") is None:
        raise RuntimeError(
            "PDF parser missing and sips fallback unavailable. "
            "Install PyMuPDF to read PDF bills."
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
            raise RuntimeError(
                f"PDF to image conversion failed: {stderr or 'unknown error'}"
            )

        # Composite onto white background to remove alpha channel artifacts.
        rgba = Image.open(png_path).convert("RGBA")
        white_bg = Image.new("RGBA", rgba.size, "white")
        white_bg.alpha_composite(rgba)
        return ocr_image(white_bg.convert("RGB"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pdf_text(path: Path) -> str:
    """
    Extract all readable text from a PDF file.

    For each page in the document:
      - If native text is available, use it directly.
      - Otherwise, render the page at 2× resolution and OCR the raster.

    Returns the concatenated text from all pages.
    Raises ``RuntimeError`` if the document contains no readable text at all.
    """
    if fitz is None:
        return _extract_pdf_text_with_sips(path)

    document = fitz.open(path)
    output_parts: list[str] = []

    try:
        for page in document:
            # Prefer native text — it is faster and more accurate.
            page_text = (page.get_text("text") or "").strip()
            if page_text:
                output_parts.append(page_text)
                continue

            # Render page as 2× image for OCR (higher DPI improves accuracy).
            matrix = fitz.Matrix(2, 2)
            pixmap = page.get_pixmap(matrix=matrix)
            image = Image.frombytes(
                "RGB", [pixmap.width, pixmap.height], pixmap.samples
            )
            ocr_text = ocr_image(image)
            if ocr_text.strip():
                output_parts.append(ocr_text)
    finally:
        document.close()

    merged = "\n".join(output_parts).strip()
    if not merged:
        raise RuntimeError("No readable text found in PDF.")
    return merged

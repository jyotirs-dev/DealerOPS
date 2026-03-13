"""
ocr.py – Low-level OCR engine
==============================
Handles all interactions with the Tesseract OCR engine, either through
the ``pytesseract`` Python binding or the raw CLI binary.

This module is intentionally *free of business logic*.  It accepts an
image and returns the recognized text — nothing more.

Functions are pure in the sense that they have no shared mutable state;
side effects are limited to subprocess calls and temp-file creation,
which are unavoidable for OCR.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

# Try the Python binding first; fall back to CLI-only mode.
try:
    import pytesseract as _pytesseract
except ImportError:
    _pytesseract = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Enhance an image for better OCR accuracy.

    Pipeline:
      1. Convert to grayscale.
      2. Auto-contrast to normalize brightness.
      3. Scale up 3× (helps Tesseract with small text).
      4. Binarize with a 170/255 threshold (clean black-on-white).

    Returns a new ``Image`` — the original is not mutated.
    """
    gray = image.convert("L")
    gray = ImageOps.autocontrast(gray)
    scaled = gray.resize((gray.width * 3, gray.height * 3))
    return scaled.point(lambda pixel: 255 if pixel > 170 else 0)


# ---------------------------------------------------------------------------
# Tesseract CLI fallback
# ---------------------------------------------------------------------------

def _run_tesseract_cli(image_path: Path, psm: int) -> str:
    """
    Invoke the ``tesseract`` binary directly and return stdout.

    Raises ``RuntimeError`` if the binary is missing or exits non-zero.

    Parameters
    ----------
    image_path:
        Path to an image file on disk.
    psm:
        Tesseract Page Segmentation Mode.
        Common values: 6 = uniform block, 11 = sparse text.
    """
    if shutil.which("tesseract") is None:
        raise RuntimeError(
            "OCR engine not found. Install tesseract to process image/scanned bills."
        )

    command = ["tesseract", str(image_path), "stdout", "--psm", str(psm)]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"Tesseract OCR failed: {stderr or 'unknown error'}")

    return result.stdout


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ocr_image(image: Image.Image) -> str:
    """
    Run OCR on an in-memory PIL image and return the recognized text.

    Strategy:
      1. Try a preprocessed version (grayscale + binarized) at PSM 11
         (sparse text — works best for invoices with scattered fields).
      2. Fall back to the original image at PSM 6 (uniform block).

    Returns an empty string if both attempts produce no text.
    """
    variants = [
        (preprocess_for_ocr(image), 11),
        (image.convert("RGB"), 6),
    ]

    for variant_image, psm in variants:
        if _pytesseract is not None:
            text = _pytesseract.image_to_string(
                variant_image, config=f"--psm {psm}"
            )
        else:
            # Save to a temp file and call the CLI binary.
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / "ocr_input.png"
                variant_image.convert("RGB").save(temp_path)
                text = _run_tesseract_cli(temp_path, psm=psm)

        if text.strip():
            return text

    return ""

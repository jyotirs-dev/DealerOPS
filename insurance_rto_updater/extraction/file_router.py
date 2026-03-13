"""
file_router.py – Route a bill file to the right extractor
=========================================================
A single pure function that decides *how* to read a file based on its
extension: PDFs go through the PDF module, everything else is treated
as an image and OCR'd directly.

Keeping this decision in one place makes it trivial to add new formats
(e.g. HEIC, AVIF) later without scattering switch-logic around.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from insurance_rto_updater.extraction.ocr import ocr_image
from insurance_rto_updater.extraction.pdf import extract_pdf_text


def extract_text_from_file(path: Path) -> str:
    """
    Extract readable text from a bill file (PDF or image).

    Parameters
    ----------
    path:
        Absolute path to the bill file on disk.

    Returns
    -------
    str:
        The full extracted text.

    Raises
    ------
    RuntimeError:
        If the file cannot be read or contains no recognizable text.
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf_text(path)

    # All other supported formats are treated as raster images.
    image = Image.open(path)
    text = ocr_image(image)
    if not text.strip():
        raise RuntimeError("No readable text found in image bill.")
    return text

"""
extraction – Text extraction from bill files
=============================================
Sub-modules:
  - **ocr**         – Low-level Tesseract OCR engine (CLI and pytesseract).
  - **pdf**         – PDF text extraction (PyMuPDF with sips+OCR fallback).
  - **text_parser** – Parse customer name and final amount from raw text.
  - **file_router** – Route a file path to the appropriate extractor.
"""

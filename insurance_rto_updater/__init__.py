"""
Insurance + RTO Sales Updater
=============================
A modular pipeline that:
  1. Extracts text from insurance / RTO bill images and PDFs (OCR).
  2. Parses customer names and amounts from the extracted text.
  3. Fuzzy-matches each bill to sales-sheet rows by customer name.
  4. Writes matched amounts back into a Google Sheet.
  5. Generates a review CSV for ambiguous / failed cases.

Architecture
------------
- **models**        – Pure data-classes shared across all layers.
- **extraction**    – OCR + text extraction (no business logic).
- **domain**        – Insurance / RTO matching and assignment rules.
- **validation**    – Comparison helpers that highlight mismatches.
- **integrations**  – Google Sheets read / write adapter.
- **orchestration** – Thin pipeline wiring everything together.
- **output**        – CSV writers for review artifacts.
"""

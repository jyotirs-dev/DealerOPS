"""
google_sheets.py – Google Sheets read / write adapter
======================================================
Encapsulates all interactions with the Google Sheets API via the
``gspread`` library.

Separation contract:
  - This module accepts *clean structured inputs* (``SheetWritePlan``,
    column indices, plain strings) — **no** business logic about
    insurance or RTO lives here.
  - Errors are re-raised as descriptive ``RuntimeError`` / ``ValueError``
    with user-friendly messages suitable for the web UI.

The adapter is a thin **class** (not pure functions) because ``gspread``
requires a stateful client object.  However, every *public method*
returns or mutates only through its explicit parameters — no hidden
globals.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from insurance_rto_updater.models import SheetData, SheetWritePlan

# ---------------------------------------------------------------------------
# Constants and compiled patterns
# ---------------------------------------------------------------------------

GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_SPREADSHEET_URL_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
_DIRECT_ID_RE = re.compile(r"^[a-zA-Z0-9-_]{20,}$")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def parse_spreadsheet_id(sheet_url: str) -> str:
    """
    Extract the spreadsheet ID from a Google Sheets URL.

    Accepts:
      - Full URL: ``https://docs.google.com/spreadsheets/d/<ID>/edit``
      - Direct ID string (≥ 20 alphanumeric characters).

    Raises ``ValueError`` for invalid inputs.
    """
    trimmed = sheet_url.strip()
    if not trimmed:
        raise ValueError("Google Sheet URL is required.")

    match = _SPREADSHEET_URL_RE.search(trimmed)
    if match:
        return match.group(1)

    if _DIRECT_ID_RE.match(trimmed):
        return trimmed

    raise ValueError(
        "Invalid Google Sheet URL. "
        "Expected a URL containing /spreadsheets/d/<id>."
    )


def col_index_to_letter(col_index: int) -> str:
    """
    Convert a 1-based column index to an Excel-style letter (1→A, 27→AA).

    Raises ``ValueError`` if ``col_index`` is not positive.
    """
    if col_index <= 0:
        raise ValueError("Column index must be positive.")

    value = col_index
    letters: list[str] = []
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


# ---------------------------------------------------------------------------
# Adapter class
# ---------------------------------------------------------------------------

class GoogleSheetsAdapter:
    """
    Reads and writes data from/to a single Google Sheet via service-account
    credentials.

    Parameters
    ----------
    sheet_url:
        Full Google Sheets URL or a bare spreadsheet ID.
    credentials_file:
        Path to the service-account JSON key file.
    sheet_name:
        Optional worksheet tab name.  ``None`` → first worksheet.
    service:
        Pre-built gspread client (used for testing with fakes).
    """

    def __init__(
        self,
        sheet_url: str,
        credentials_file: Path,
        sheet_name: str | None = None,
        service: Any | None = None,
    ) -> None:
        self.sheet_url = sheet_url.strip()
        self.spreadsheet_id = parse_spreadsheet_id(self.sheet_url)
        self.credentials_file = credentials_file
        self.sheet_name = (sheet_name or "").strip() or None
        self._client = service

    # ---- Client lifecycle --------------------------------------------------

    def _build_client(self) -> Any:
        """Lazily construct the gspread client on first use."""
        if self._client is not None:
            return self._client

        if not self.credentials_file.exists():
            raise ValueError(
                f"Service account file not found: {self.credentials_file}"
            )

        try:
            import gspread
        except Exception as exc:
            raise RuntimeError(
                "Google Sheets dependencies missing. Install gspread, "
                "google-api-python-client, google-auth-httplib2, and "
                "google-auth-oauthlib."
            ) from exc

        self._client = gspread.service_account(
            filename=str(self.credentials_file)
        )
        if hasattr(self._client, "set_timeout"):
            try:
                self._client.set_timeout(60)
            except Exception:
                pass
        return self._client

    # ---- Error handling ----------------------------------------------------

    @staticmethod
    def _raise_contextual_error(exc: Exception) -> None:
        """
        Wrap Google API exceptions in user-friendly messages.

        Common patterns:
          - Timeout / DNS → suggest checking network.
          - 403 / permission → suggest sharing sheet with service account.
        """
        message = str(exc)
        lowered = message.lower()

        if "timed out" in lowered or "unable to find the server" in lowered:
            raise RuntimeError(
                "Google API timeout/network error. "
                "Check internet access and retry."
            ) from exc

        if (
            "permission" in lowered
            or "insufficient" in lowered
            or "403" in lowered
        ):
            raise RuntimeError(
                "Google Sheet access denied. Share the sheet with "
                "service-account email as Editor."
            ) from exc

        raise RuntimeError(f"Google Sheets API error: {message}") from exc

    # ---- Spreadsheet / worksheet resolution --------------------------------

    def _open_spreadsheet(self) -> Any:
        client = self._build_client()
        try:
            return client.open_by_key(self.spreadsheet_id)
        except Exception as exc:
            self._raise_contextual_error(exc)

    def _resolve_worksheet(self, spreadsheet: Any) -> Any:
        if self.sheet_name is None:
            worksheet = spreadsheet.get_worksheet(0)
            if worksheet is None:
                raise ValueError("No worksheets found in Google Sheet.")
            return worksheet

        try:
            return spreadsheet.worksheet(self.sheet_name)
        except Exception:
            worksheets = spreadsheet.worksheets()
            available = [ws.title for ws in worksheets]
            raise ValueError(
                f"Worksheet '{self.sheet_name}' not found. "
                f"Available: {', '.join(filter(None, available))}"
            )

    # ---- Public API --------------------------------------------------------

    def load_sheet_data(self) -> SheetData:
        """
        Fetch the header row and all data rows from the target worksheet.

        Raises ``ValueError`` if the worksheet is empty or the header is blank.
        """
        spreadsheet = self._open_spreadsheet()
        worksheet = self._resolve_worksheet(spreadsheet)
        sheet_title = worksheet.title

        try:
            values = worksheet.get_all_values()
        except Exception as exc:
            self._raise_contextual_error(exc)

        if not values:
            raise ValueError("Selected worksheet is empty.")

        header_row = [str(item).strip() for item in values[0]]
        if not any(header_row):
            raise ValueError("Header row is empty in selected worksheet.")

        data_rows = [
            [str(cell).strip() for cell in row] for row in values[1:]
        ]
        return SheetData(
            spreadsheet_id=self.spreadsheet_id,
            spreadsheet_url=self.sheet_url,
            sheet_title=sheet_title,
            header_row=header_row,
            data_rows=data_rows,
        )

    def apply_write_plan(
        self,
        sheet_title: str,
        write_plan: SheetWritePlan,
    ) -> None:
        """
        Execute a ``SheetWritePlan`` against the Google Sheet.

        Steps:
          1. Optionally clear the insurance / RTO columns.
          2. Batch-update cells with new values.
        """
        spreadsheet = self._open_spreadsheet()

        if self.sheet_name == sheet_title:
            worksheet = self._resolve_worksheet(spreadsheet)
        else:
            try:
                worksheet = spreadsheet.worksheet(sheet_title)
            except Exception:
                raise ValueError(f"Worksheet '{sheet_title}' not found.")

        # Step 1: clear columns (if requested).
        if (
            write_plan.clear_to_row >= write_plan.clear_from_row
            and write_plan.clear_columns
        ):
            ranges = [
                f"{col_index_to_letter(col)}{write_plan.clear_from_row}:"
                f"{col_index_to_letter(col)}{write_plan.clear_to_row}"
                for col in write_plan.clear_columns
            ]
            try:
                worksheet.batch_clear(ranges)
            except Exception as exc:
                self._raise_contextual_error(exc)

        # Step 2: write new values.
        if not write_plan.value_updates:
            return

        payload = [
            {
                "range": (
                    f"{col_index_to_letter(item.col_index)}{item.row_index}"
                ),
                "values": [[item.value]],
            }
            for item in write_plan.value_updates
        ]
        try:
            worksheet.batch_update(
                payload,
                value_input_option="USER_ENTERED",
            )
        except Exception as exc:
            self._raise_contextual_error(exc)

from __future__ import annotations

import unittest
from pathlib import Path

from sheets_adapter import (
    CellValueUpdate,
    GoogleSheetsAdapter,
    SheetWritePlan,
    col_index_to_letter,
    parse_spreadsheet_id,
)


class FakeWorksheet:
    def __init__(self, title, values):
        self.title = title
        self.values = values
        self.batch_clear_calls = []
        self.batch_update_calls = []

    def get_all_values(self):
        return self.values

    def batch_clear(self, ranges):
        self.batch_clear_calls.append(ranges)

    def batch_update(self, data, value_input_option="RAW"):
        self.batch_update_calls.append(
            {"data": data, "value_input_option": value_input_option}
        )


class FakeSpreadsheet:
    def __init__(self, worksheets):
        self._worksheets = worksheets

    def get_worksheet(self, index):
        if index < 0 or index >= len(self._worksheets):
            return None
        return self._worksheets[index]

    def worksheet(self, name):
        for ws in self._worksheets:
            if ws.title == name:
                return ws
        raise ValueError("Worksheet not found")

    def worksheets(self):
        return list(self._worksheets)


class FakeGspreadClient:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet
        self.open_by_key_calls = []

    def open_by_key(self, key):
        self.open_by_key_calls.append(key)
        return self.spreadsheet


class ParseSpreadsheetIdTests(unittest.TestCase):
    def test_parses_full_google_sheet_url(self):
        url = "https://docs.google.com/spreadsheets/d/abc123_XYZ-99/edit#gid=0"
        self.assertEqual(parse_spreadsheet_id(url), "abc123_XYZ-99")

    def test_accepts_direct_spreadsheet_id(self):
        spreadsheet_id = "1A2b3C4d5E6f7G8h9I0jKlmNoP"
        self.assertEqual(parse_spreadsheet_id(spreadsheet_id), spreadsheet_id)

    def test_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            parse_spreadsheet_id("not-a-google-sheet")


class ColIndexTests(unittest.TestCase):
    def test_col_index_to_letter(self):
        self.assertEqual(col_index_to_letter(1), "A")
        self.assertEqual(col_index_to_letter(26), "Z")
        self.assertEqual(col_index_to_letter(27), "AA")
        self.assertEqual(col_index_to_letter(52), "AZ")


class AdapterFlowTests(unittest.TestCase):
    def test_load_sheet_data_and_apply_write_plan(self):
        sales_ws = FakeWorksheet(
            title="Sales Jan",
            values=[
                ["Customer Name", "Insurance Amount", "RTO Amount"],
                ["ANSHU SINGH SISODIYA", "", ""],
                ["OTHER", "", ""],
            ],
        )
        archive_ws = FakeWorksheet(title="Archive", values=[["A"]])
        fake_client = FakeGspreadClient(
            spreadsheet=FakeSpreadsheet(worksheets=[sales_ws, archive_ws])
        )
        adapter = GoogleSheetsAdapter(
            sheet_url="https://docs.google.com/spreadsheets/d/1A2B3C4D5E6F7G8H9I0J/edit",
            sheet_name="Sales Jan",
            credentials_file=Path("/tmp/fake.json"),
            service=fake_client,
        )

        sheet_data = adapter.load_sheet_data()
        self.assertEqual(sheet_data.sheet_title, "Sales Jan")
        self.assertEqual(sheet_data.header_row[0], "Customer Name")
        self.assertEqual(len(sheet_data.data_rows), 2)

        write_plan = SheetWritePlan(
            clear_from_row=2,
            clear_to_row=3,
            clear_columns=[2, 3],
            value_updates=[CellValueUpdate(row_index=2, col_index=2, value=5049.0)],
        )
        adapter.apply_write_plan(sheet_title=sheet_data.sheet_title, write_plan=write_plan)

        self.assertEqual(fake_client.open_by_key_calls[0], "1A2B3C4D5E6F7G8H9I0J")
        self.assertEqual(len(sales_ws.batch_clear_calls), 1)
        self.assertEqual(len(sales_ws.batch_update_calls), 1)
        clear_ranges = sales_ws.batch_clear_calls[0]
        self.assertIn("B2:B3", clear_ranges)
        self.assertIn("C2:C3", clear_ranges)

        update_call = sales_ws.batch_update_calls[0]
        self.assertEqual(update_call["value_input_option"], "USER_ENTERED")
        self.assertEqual(update_call["data"][0]["range"], "B2")


if __name__ == "__main__":
    unittest.main()

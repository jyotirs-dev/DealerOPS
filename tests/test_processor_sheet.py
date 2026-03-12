from __future__ import annotations

import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from processor import ProcessingConfig, run_processing_for_sheet


def build_config() -> ProcessingConfig:
    return ProcessingConfig(
        sheet_name="Sales",
        customer_header="Customer Name",
        insurance_header="Insurance Amount",
        rto_header="RTO Amount",
        customer_labels=["Insured", "Received From"],
        amount_labels=["Final Amount", "Grand Total"],
        amount_position="same_line",
        name_threshold=95.0,
        clear_existing=True,
    )


class ProcessingForSheetTests(unittest.TestCase):
    def test_unique_match_generates_write_plan(self):
        header_row = ["Customer Name", "Insurance Amount", "RTO Amount"]
        data_rows = [
            ["ANSHU SINGH SISODIYA", "", ""],
            ["OTHER CUSTOMER", "", ""],
        ]
        config = build_config()

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("processor.extract_text", return_value="dummy text"),
                patch("processor.extract_customer", return_value=("ANSHU SINGH SISODIYA", None)),
                patch("processor.extract_final_amount", return_value=(Decimal("5049"), None)),
            ):
                result, write_plan = run_processing_for_sheet(
                    header_row=header_row,
                    data_rows=data_rows,
                    insurance_paths=[Path("insurance_1.pdf")],
                    rto_paths=[],
                    output_dir=Path(temp_dir),
                    config=config,
                    sheet_reference="https://docs.google.com/spreadsheets/d/test",
                    sheet_title="Sales",
                )

        self.assertEqual(result.bills_processed, 1)
        self.assertEqual(result.bills_updated, 1)
        self.assertEqual(result.rows_updated, 1)
        self.assertEqual(len(write_plan.value_updates), 1)
        self.assertEqual(write_plan.value_updates[0].row_index, 2)
        self.assertEqual(write_plan.value_updates[0].col_index, 2)
        self.assertEqual(write_plan.clear_columns, [2, 3])
        self.assertEqual(write_plan.clear_from_row, 2)
        self.assertEqual(write_plan.clear_to_row, 3)

    def test_multiple_sales_row_match_goes_to_review(self):
        header_row = ["Customer Name", "Insurance Amount", "RTO Amount"]
        data_rows = [
            ["ANSHU SINGH SISODIYA", "", ""],
            ["ANSHU SINGH SISODIYA", "", ""],
        ]
        config = build_config()

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("processor.extract_text", return_value="dummy text"),
                patch("processor.extract_customer", return_value=("ANSHU SINGH SISODIYA", None)),
                patch("processor.extract_final_amount", return_value=(Decimal("5049"), None)),
            ):
                result, write_plan = run_processing_for_sheet(
                    header_row=header_row,
                    data_rows=data_rows,
                    insurance_paths=[Path("insurance_1.pdf")],
                    rto_paths=[],
                    output_dir=Path(temp_dir),
                    config=config,
                    sheet_reference="https://docs.google.com/spreadsheets/d/test",
                    sheet_title="Sales",
                )

            self.assertEqual(result.multi_match, 1)
            self.assertEqual(result.bills_updated, 0)
            self.assertEqual(len(write_plan.value_updates), 0)

            with result.review_csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reason"], "MULTIPLE_SALES_ROWS")

    def test_multiple_bills_same_row_type_flagged(self):
        header_row = ["Customer Name", "Insurance Amount", "RTO Amount"]
        data_rows = [["ANSHU SINGH SISODIYA", "", ""]]
        config = build_config()

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch("processor.extract_text", return_value="dummy text"),
                patch("processor.extract_customer", return_value=("ANSHU SINGH SISODIYA", None)),
                patch(
                    "processor.extract_final_amount",
                    side_effect=[(Decimal("5049"), None), (Decimal("4000"), None)],
                ),
            ):
                result, write_plan = run_processing_for_sheet(
                    header_row=header_row,
                    data_rows=data_rows,
                    insurance_paths=[Path("insurance_1.pdf"), Path("insurance_2.pdf")],
                    rto_paths=[],
                    output_dir=Path(temp_dir),
                    config=config,
                    sheet_reference="https://docs.google.com/spreadsheets/d/test",
                    sheet_title="Sales",
                )

            self.assertEqual(result.row_conflicts, 2)
            self.assertEqual(result.bills_updated, 0)
            self.assertEqual(len(write_plan.value_updates), 0)

            with result.review_csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reason"], "MULTIPLE_BILLS_FOR_ROW_TYPE")


if __name__ == "__main__":
    unittest.main()

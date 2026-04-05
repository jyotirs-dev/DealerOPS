"""
test_validation.py – Unit tests for the validation/comparator module
=====================================================================
Tests header lookup, sales-row building, and write-plan construction.
All functions under test are pure.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from insurance_rto_updater.models import Assignment
from insurance_rto_updater.validation.comparator import (
    build_sales_rows,
    build_sheet_write_plan,
    find_header_indices,
)


class FindHeaderIndicesTests(unittest.TestCase):
    """Tests for mapping header names to column indices."""

    def test_finds_exact_headers(self):
        header_row = ["Customer Name", "Insurance Amount", "RTO Amount"]
        c, i, r = find_header_indices(
            header_row, "Customer Name", "Insurance Amount", "RTO Amount"
        )
        self.assertEqual(c, 1)
        self.assertEqual(i, 2)
        self.assertEqual(r, 3)

    def test_case_insensitive_match(self):
        header_row = ["customer name", "INSURANCE AMOUNT", "Rto Amount"]
        c, i, r = find_header_indices(
            header_row, "Customer Name", "insurance amount", "RTO AMOUNT"
        )
        self.assertEqual(c, 1)
        self.assertEqual(i, 2)
        self.assertEqual(r, 3)

    def test_raises_on_missing_header(self):
        header_row = ["Customer Name", "Insurance Amount"]
        with self.assertRaises(ValueError) as ctx:
            find_header_indices(
                header_row, "Customer Name", "Insurance Amount", "RTO Amount"
            )
        self.assertIn("RTO Amount", str(ctx.exception))


class BuildSalesRowsTests(unittest.TestCase):
    """Tests for building SalesRow records from sheet data."""

    def test_builds_rows_with_customer_values(self):
        data_rows = [
            ["BADARASINGH C/O NAGUSINGH", "", ""],
            ["", "", ""],  # empty customer — should be skipped
            ["OTHER", "", ""],
        ]
        rows, max_row = build_sales_rows(data_rows, customer_col=1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].customer_raw, "BADARASINGH C/O NAGUSINGH")
        self.assertEqual(rows[0].customer_norm, "badarasingh")
        self.assertEqual(rows[0].row_index, 2)
        self.assertEqual(rows[1].row_index, 4)
        self.assertEqual(max_row, 4)


class BuildSheetWritePlanTests(unittest.TestCase):
    """Tests for constructing the sheet write plan."""

    def test_creates_updates_for_accepted_assignments(self):
        assignments = [
            Assignment("insurance", "a.pdf", 2, Decimal("5000"), "A", 98.0),
            Assignment("rto", "b.pdf", 3, Decimal("3000"), "B", 96.0),
        ]
        plan = build_sheet_write_plan(
            accepted_assignments=assignments,
            insurance_col=2,
            rto_col=3,
            max_row=4,
            clear_existing=True,
        )
        self.assertEqual(len(plan.value_updates), 2)
        # Insurance bill → insurance column (2).
        self.assertEqual(plan.value_updates[0].col_index, 2)
        self.assertEqual(plan.value_updates[0].value, 5000.0)
        # RTO bill → RTO column (3).
        self.assertEqual(plan.value_updates[1].col_index, 3)
        self.assertEqual(plan.value_updates[1].value, 3000.0)
        # Clear columns should be set.
        self.assertEqual(plan.clear_columns, [2, 3])

    def test_no_clear_when_disabled(self):
        plan = build_sheet_write_plan(
            accepted_assignments=[],
            insurance_col=2,
            rto_col=3,
            max_row=4,
            clear_existing=False,
        )
        self.assertEqual(plan.clear_columns, [])


if __name__ == "__main__":
    unittest.main()

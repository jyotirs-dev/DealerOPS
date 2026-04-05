"""
test_domain.py – Unit tests for domain logic modules
======================================================
Tests normalization, matching, and assignment individually.
These tests import directly from the new package (no shims).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from insurance_rto_updater.domain import matching as matching_module
from insurance_rto_updater.domain.normalization import (
    normalize_customer_name,
    normalize_text,
)
from insurance_rto_updater.domain.matching import score_all_candidates, serialize_candidates
from insurance_rto_updater.domain.assignment import (
    assign_bill_to_row,
    assign_bill_to_row_by_filename_first_name,
    detect_row_conflicts,
)
from insurance_rto_updater.models import Assignment, BillParseResult, ReviewRow, SalesRow


class NormalizationTests(unittest.TestCase):
    """Tests for the normalize_text utility."""

    def test_lowercases_and_strips(self):
        self.assertEqual(normalize_text("  HELLO World  "), "hello world")

    def test_removes_special_characters(self):
        self.assertEqual(normalize_text("ANSHU—Singh_42"), "anshu singh 42")

    def test_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_text("a    b   c"), "a b c")

    def test_normalize_customer_name_strips_relationship_suffix(self):
        self.assertEqual(
            normalize_customer_name("BADARASINGH C/O NAGUSINGH"),
            "badarasingh",
        )


class MatchingTests(unittest.TestCase):
    """Tests for fuzzy name scoring."""

    def _make_sales_rows(self, names: list[str]) -> list[SalesRow]:
        return [
            SalesRow(
                row_index=i + 2,
                customer_raw=name,
                customer_norm=normalize_customer_name(name),
            )
            for i, name in enumerate(names)
        ]

    def test_exact_match_scores_highest(self):
        rows = self._make_sales_rows(["ANSHU SINGH", "OTHER PERSON"])
        scored = score_all_candidates("ANSHU SINGH", rows)
        # The first result should be the exact match.
        self.assertEqual(scored[0][0].customer_raw, "ANSHU SINGH")
        self.assertGreater(scored[0][1], 90)

    def test_no_rows_returns_empty(self):
        scored = score_all_candidates("ANSHU", [])
        self.assertEqual(scored, [])

    def test_relationship_suffix_in_sales_row_does_not_block_match(self):
        rows = self._make_sales_rows(
            [
                "BADARASINGH C/O NAGUSINGH",
                "MANGU SINGH S/O RAM SINGH JI",
                "AANNAD SINGH S/O NEN SINGH",
            ]
        )
        scored = score_all_candidates("BADARA SINGH", rows)
        self.assertEqual(scored[0][0].customer_raw, "BADARASINGH C/O NAGUSINGH")
        self.assertGreaterEqual(scored[0][1], 95.0)

    def test_missing_query_token_caps_subset_score(self):
        rows = self._make_sales_rows(
            [
                "VIRENDRA VALIYA S/O GIRDHARI",
                "VIRENDRA S/O KANHAIYALAL",
            ]
        )
        scored = score_all_candidates("VIRENDRA VALIYA", rows)
        self.assertEqual(scored[0][0].customer_raw, "VIRENDRA VALIYA S/O GIRDHARI")
        self.assertEqual(scored[0][1], 100.0)
        self.assertEqual(scored[1][0].customer_raw, "VIRENDRA S/O KANHAIYALAL")
        self.assertEqual(scored[1][1], 50.0)

    def test_missing_query_token_caps_subset_score_with_rapidfuzz(self):
        rows = self._make_sales_rows(
            [
                "VIRENDRA VALIYA S/O GIRDHARI",
                "VIRENDRA S/O KANHAIYALAL",
            ]
        )

        class FakeFuzz:
            @staticmethod
            def WRatio(query: str, candidate: str) -> float:
                if candidate == "virendra":
                    return 90.0
                return 100.0

            @staticmethod
            def token_set_ratio(query: str, candidate: str) -> float:
                return 100.0

        previous = matching_module._fuzz
        matching_module._fuzz = FakeFuzz()
        try:
            scored = score_all_candidates("VIRENDRA VALIYA", rows)
        finally:
            matching_module._fuzz = previous

        self.assertEqual(scored[0][0].customer_raw, "VIRENDRA VALIYA S/O GIRDHARI")
        self.assertEqual(scored[0][1], 100.0)
        self.assertEqual(scored[1][0].customer_raw, "VIRENDRA S/O KANHAIYALAL")
        self.assertEqual(scored[1][1], 50.0)

    def test_serialize_candidates_format(self):
        rows = self._make_sales_rows(["ABC"])
        result = serialize_candidates([(rows[0], 95.5)])
        self.assertIn("row=2", result)
        self.assertIn("score=95.50", result)
        self.assertIn("customer=ABC", result)


class AssignmentTests(unittest.TestCase):
    """Tests for bill → row assignment logic."""

    def _make_bill(self, customer: str, amount: str = "5000") -> BillParseResult:
        return BillParseResult(
            bill_type="insurance",
            file_name="test.pdf",
            raw_text="",
            customer_name=customer,
            amount=Decimal(amount),
        )

    def _make_sales_rows(self, names: list[str]) -> list[SalesRow]:
        return [
            SalesRow(
                row_index=i + 2,
                customer_raw=name,
                customer_norm=normalize_customer_name(name),
            )
            for i, name in enumerate(names)
        ]

    def test_single_exact_match_returns_assignment(self):
        bill = self._make_bill("ANSHU SINGH SISODIYA")
        rows = self._make_sales_rows(["ANSHU SINGH SISODIYA", "OTHER PERSON"])
        result = assign_bill_to_row(bill, rows, name_threshold=95.0)
        self.assertIsInstance(result, Assignment)
        self.assertEqual(result.row_index, 2)

    def test_no_match_returns_review(self):
        bill = self._make_bill("COMPLETELY DIFFERENT NAME")
        rows = self._make_sales_rows(["ANSHU SINGH SISODIYA"])
        result = assign_bill_to_row(bill, rows, name_threshold=95.0)
        self.assertIsInstance(result, ReviewRow)
        self.assertEqual(result.reason, "NO_MATCH")

    def test_sheet_relationship_suffix_still_allows_assignment(self):
        bill = self._make_bill("BADARA SINGH")
        rows = self._make_sales_rows(
            [
                "BADARASINGH C/O NAGUSINGH",
                "MANGU SINGH S/O RAM SINGH JI",
            ]
        )
        result = assign_bill_to_row(bill, rows, name_threshold=95.0)
        self.assertIsInstance(result, Assignment)
        self.assertEqual(result.row_index, 2)

    def test_filename_first_name_fallback_returns_unique_assignment(self):
        bill = BillParseResult(
            bill_type="rto",
            file_name="virendra_valiya_girdhari_2_feb.pdf",
            raw_text="",
            amount=Decimal("5937"),
            customer_error="CUSTOMER_LABEL_NOT_FOUND",
        )
        rows = self._make_sales_rows(
            ["VIRENDRA VALIYA S/O GIRDHARI", "OTHER PERSON"]
        )
        result = assign_bill_to_row_by_filename_first_name(bill, rows)
        self.assertIsInstance(result, Assignment)
        assert isinstance(result, Assignment)
        self.assertEqual(result.row_index, 2)
        self.assertEqual(result.score, 100.0)

    def test_filename_first_name_fallback_rejects_ambiguous_matches(self):
        bill = BillParseResult(
            bill_type="rto",
            file_name="virendra_valiya_girdhari_2_feb.pdf",
            raw_text="",
            amount=Decimal("5937"),
            customer_error="CUSTOMER_LABEL_NOT_FOUND",
        )
        rows = self._make_sales_rows(
            [
                "VIRENDRA VALIYA S/O GIRDHARI",
                "VIRENDRA S/O KANHAIYALAL",
            ]
        )
        result = assign_bill_to_row_by_filename_first_name(bill, rows)
        self.assertIsNone(result)

    def test_detect_row_conflicts_accepts_unique(self):
        assignments = [
            Assignment("insurance", "a.pdf", 2, Decimal("1000"), "A", 98.0),
            Assignment("rto", "b.pdf", 2, Decimal("2000"), "A", 97.0),
        ]
        # Different bill types on same row = no conflict.
        accepted, conflicts = detect_row_conflicts(assignments)
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(conflicts), 0)

    def test_detect_row_conflicts_flags_duplicate_type(self):
        assignments = [
            Assignment("insurance", "a.pdf", 2, Decimal("1000"), "A", 98.0),
            Assignment("insurance", "b.pdf", 2, Decimal("2000"), "A", 97.0),
        ]
        # Same bill type on same row = conflict.
        accepted, conflicts = detect_row_conflicts(assignments)
        self.assertEqual(len(accepted), 0)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].reason, "MULTIPLE_BILLS_FOR_ROW_TYPE")


if __name__ == "__main__":
    unittest.main()

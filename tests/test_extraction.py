"""
test_extraction.py – Unit tests for the text parser
=====================================================
Tests customer name and amount extraction from raw bill text.
These functions are pure, so no mocking is needed.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from insurance_rto_updater.extraction.text_parser import (
    extract_customer,
    extract_final_amount,
)


class ExtractCustomerTests(unittest.TestCase):
    """Tests for customer name extraction from bill text."""

    def test_extracts_customer_from_insured_label(self):
        text = "Policy No: 12345\nInsured: Ramesh Kumar\nPremium: 5000"
        customer, error = extract_customer(text, ["Insured"])
        self.assertIsNone(error)
        self.assertEqual(customer, "Ramesh Kumar")

    def test_extracts_customer_from_next_line(self):
        text = "Received From:\nSuresh Sharma\nAmount: 3000"
        customer, error = extract_customer(text, ["Received From"])
        self.assertIsNone(error)
        self.assertEqual(customer, "Suresh Sharma")

    def test_strips_relationship_suffixes_on_same_line(self):
        cases = [
            ("Insured: VIRENDRA VALIYA S/O GIRDHARI", "VIRENDRA VALIYA"),
            ("Insured: VIRENDRA C/O KANHAIYALAL", "VIRENDRA"),
            ("Insured: KRISHNA BAI W/O SACHIN PARIHAR", "KRISHNA BAI"),
        ]

        for line, expected in cases:
            with self.subTest(line=line):
                customer, error = extract_customer(
                    f"{line}\nAmount: 1000",
                    ["Insured"],
                )
                self.assertIsNone(error)
                self.assertEqual(customer, expected)

    def test_strips_relationship_suffixes_on_next_line(self):
        text = "Received From:\nVIRENDRA C/O KANHAIYALAL\nAmount: 3000"
        customer, error = extract_customer(text, ["Received From"])
        self.assertIsNone(error)
        self.assertEqual(customer, "VIRENDRA")

    def test_returns_error_for_empty_text(self):
        customer, error = extract_customer("", ["Insured"])
        self.assertIsNone(customer)
        self.assertEqual(error, "EMPTY_TEXT")

    def test_returns_error_when_label_not_found(self):
        text = "Some random text without any labels"
        customer, error = extract_customer(text, ["Insured"])
        self.assertIsNone(customer)
        self.assertEqual(error, "CUSTOMER_LABEL_NOT_FOUND")

    def test_rejects_insurance_keywords_as_names(self):
        text = "Insured: Optional Cover Passenger\nAmount: 1000"
        customer, error = extract_customer(text, ["Insured"])
        # "Optional Cover Passenger" contains blocked words, should be rejected.
        self.assertIsNone(customer)


class ExtractFinalAmountTests(unittest.TestCase):
    """Tests for final amount extraction from bill text."""

    def test_extracts_same_line_amount(self):
        text = "Grand Total: Rs. 15,000.00"
        amount, error = extract_final_amount(text, ["Grand Total"], "same_line")
        self.assertIsNone(error)
        self.assertEqual(amount, Decimal("15000.00"))

    def test_extracts_next_line_amount(self):
        text = "Final Amount\n12,500"
        amount, error = extract_final_amount(text, ["Final Amount"], "next_line")
        self.assertIsNone(error)
        self.assertEqual(amount, Decimal("12500"))

    def test_returns_error_for_empty_text(self):
        amount, error = extract_final_amount("", ["Total"], "same_line")
        self.assertIsNone(amount)
        self.assertEqual(error, "EMPTY_TEXT")

    def test_returns_error_when_label_not_found(self):
        text = "Some text without amount labels"
        amount, error = extract_final_amount(text, ["Grand Total"], "same_line")
        self.assertIsNone(amount)
        self.assertEqual(error, "FINAL_AMOUNT_LABEL_NOT_FOUND")

    def test_filters_out_tiny_amounts(self):
        # Amounts < 10 should be rejected (stamp duty, tokens).
        text = "Grand Total: 5"
        amount, error = extract_final_amount(text, ["Grand Total"], "same_line")
        self.assertIsNone(amount)

    def test_rejects_invalid_position(self):
        text = "Grand Total: 5000"
        amount, error = extract_final_amount(text, ["Grand Total"], "invalid")
        self.assertIsNone(amount)
        self.assertEqual(error, "INVALID_AMOUNT_POSITION")


class ExtractAmountEdgeCasesTests(unittest.TestCase):
    """Tests for Indian-format amount parsing edge cases."""

    def test_indian_lakh_format(self):
        text = "Final Amount: 1,00,000"
        amount, error = extract_final_amount(text, ["Final Amount"], "same_line")
        self.assertIsNone(error)
        self.assertEqual(amount, Decimal("100000"))

    def test_decimal_amount(self):
        text = "Grand Total: 5,049.50"
        amount, error = extract_final_amount(text, ["Grand Total"], "same_line")
        self.assertIsNone(error)
        self.assertEqual(amount, Decimal("5049.50"))


if __name__ == "__main__":
    unittest.main()

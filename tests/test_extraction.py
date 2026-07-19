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
    extract_insurance_report_rows,
    extract_pay_in_slip_rows,
)

INSURANCE_REPORT_TEXT = """MIS BUSINESS REPORT USER WISE

S.No.
User Name
Policy
Type
Policy Number
Customer
Name
Start
Date
OD
Premium
NCB
ND
Cover
RTI
Cover
RSA
addons
Gross
Premium
1.
MAHENDRA61835
N
993792623750035786
VIRENDRA
VALIYA
2/2/2026
8:00:28
PM
851
0
YES
NO
NO
5548
2.
MAHENDRA61835
N
993792623750039494 IMAM SHAH
2/6/2026
5:12:13
PM
802
0
YES
NO
NO
5491
Total
1653
0
11039
"""


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


class InsuranceReportExtractionTests(unittest.TestCase):
    """Tests for parsing multi-row insurance MIS reports."""

    def test_extracts_customer_rows_from_insurance_report(self):
        rows = extract_insurance_report_rows(INSURANCE_REPORT_TEXT, "report.pdf")
        self.assertIsNotNone(rows)
        assert rows is not None

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].file_name, "report.pdf [S.No. 1]")
        self.assertEqual(rows[0].customer_name, "VIRENDRA VALIYA")
        self.assertEqual(rows[0].amount, Decimal("5548"))
        self.assertEqual(rows[1].file_name, "report.pdf [S.No. 2]")
        self.assertEqual(rows[1].customer_name, "IMAM SHAH")
        self.assertEqual(rows[1].amount, Decimal("5491"))

    def test_returns_none_for_standard_insurance_bill_text(self):
        rows = extract_insurance_report_rows(
            "Insured: Ramesh Kumar\nGrand Total: 5400",
            "bill.pdf",
        )
        self.assertIsNone(rows)


class PayInSlipExtractionTests(unittest.TestCase):
    """Tests for parsing multi-row HIBIPL Pay-in-slip PDF reports."""

    def test_extracts_pay_in_slip_rows(self):
        mock_text = """Pay-In-Slip Details
Insurance for Hero MotoCorp Vehicles
Pay-in-Slip
Policy Details
S. No. Policy No.
Policy
Date
Customer Name
Policy Status
Executive Name
Premium
1
993792623750103274
May 8
2026
Mr LAKSHMAN BAGRI Fresh
MAHENDRA61835
5524
2
993792623750103271
May 8
2026
Mr VIKRAM .
Fresh
MAHENDRA61835
5583
3
993792623750083708
Apr 3 2026 Mr JORAVER SINGH
BHATI
Fresh
MAHENDRA61835
5682
Total Amount     16789
"""
        rows = extract_pay_in_slip_rows(mock_text, "payinslip.pdf")
        self.assertIsNotNone(rows)
        assert rows is not None
        self.assertEqual(len(rows), 3)

        self.assertEqual(rows[0].file_name, "payinslip.pdf [S.No. 1]")
        self.assertEqual(rows[0].customer_name, "LAKSHMAN BAGRI")
        self.assertEqual(rows[0].amount, Decimal("5524"))

        self.assertEqual(rows[1].file_name, "payinslip.pdf [S.No. 2]")
        self.assertEqual(rows[1].customer_name, "VIKRAM")
        self.assertEqual(rows[1].amount, Decimal("5583"))

        self.assertEqual(rows[2].file_name, "payinslip.pdf [S.No. 3]")
        self.assertEqual(rows[2].customer_name, "JORAVER SINGH BHATI")
        self.assertEqual(rows[2].amount, Decimal("5682"))

    def test_returns_none_for_standard_bill_text(self):
        rows = extract_pay_in_slip_rows(
            "Insured: Ramesh Kumar\nGrand Total: 5400",
            "bill.pdf",
        )
        self.assertIsNone(rows)


if __name__ == "__main__":
    unittest.main()

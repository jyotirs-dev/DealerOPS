"""
amounts.py – Bill-type-specific amount adjustments
==================================================
Keeps post-extraction amount rules in the domain layer so the pipeline can
stay orchestration-only.
"""
from __future__ import annotations

from decimal import Decimal


RTO_AGENT_FEE = Decimal("500")


def finalize_bill_amount(
    bill_type: str,
    amount: Decimal | None,
) -> Decimal | None:
    """
    Apply bill-type-specific adjustments to an extracted amount.

    RTO bills include a fixed agent fee of ₹500 in the final written value.
    """
    if amount is None:
        return None

    if bill_type.strip().lower() == "rto":
        return amount + RTO_AGENT_FEE

    return amount

from datetime import date
from decimal import Decimal

import pytest

from itcguard.normalize import (
    InvoiceNormalizationWarning,
    normalize_gstin,
    normalize_invoice_number,
    parse_decimal_amount,
    parse_invoice_date,
)


def test_invoice_number_handles_export_punctuation_and_numeric_runs() -> None:
    assert normalize_invoice_number("  fy24-25 / inv_000-001.002 ") == "FY2425INV012"
    assert normalize_invoice_number(
        "FY24-25/000123/2024-25",
        financial_year_prefix="FY24-25",
        financial_year_suffix="2024-25",
    ) == "123"


def test_gstin_is_trimmed_uppercased_and_invalid_length_is_nonfatal() -> None:
    warnings: list[str] = []
    with pytest.warns(InvoiceNormalizationWarning, match="expected 15"):
        result = normalize_gstin(" abc123 ", warnings_list=warnings)
    assert result == "ABC123"
    assert warnings and "invalid length" in warnings[0]


def test_dates_accept_supported_formats_and_reject_ambiguity() -> None:
    assert parse_invoice_date("05-04-2026") == date(2026, 4, 5)
    assert parse_invoice_date("13/04/2026") == date(2026, 4, 13)
    assert parse_invoice_date("2026-04-05") == date(2026, 4, 5)
    with pytest.raises(ValueError, match="ambiguous"):
        parse_invoice_date("05/04/2026")
    with pytest.raises(ValueError, match="invalid"):
        parse_invoice_date("31-02-2026")


def test_amount_parser_uses_decimal_and_accepts_rupees_and_indian_grouping() -> None:
    assert parse_decimal_amount("₹ 1,23,456.78") == Decimal("123456.78")
    assert parse_decimal_amount("(₹2,000.50)") == Decimal("-2000.50")
    with pytest.raises(ValueError, match="malformed"):
        parse_decimal_amount("₹ 1,2,34.00")

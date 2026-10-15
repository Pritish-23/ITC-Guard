from datetime import date
from decimal import Decimal

from itcguard import __version__
from itcguard.cli import build_parser
from itcguard.models import Invoice, InvoiceSource, MatchResult, MatchStatus, ReconciliationReport
from itcguard.settings import ReconciliationSettings


def test_package_version_is_defined() -> None:
    assert __version__ == "0.1.0"


def test_reconcile_arguments_are_defined() -> None:
    args = build_parser().parse_args(
        [
            "reconcile",
            "--books",
            "books.csv",
            "--gstr2b",
            "2b.csv",
            "--mapping",
            "mapping.json",
        ]
    )
    assert args.command == "reconcile"
    assert args.books == "books.csv"


def test_invoice_uses_decimal_tax_math() -> None:
    invoice = Invoice(
        source=InvoiceSource.BOOKS,
        row_id="books-1",
        supplier_gstin="27AAAAA0000A1Z5",
        supplier_name="Example Supplier",
        invoice_number_raw="INV/001",
        invoice_number_norm="INV001",
        invoice_date=date(2026, 10, 1),
        taxable_value="10000.00",
        igst="1800.00",
        cgst="0",
        sgst="0",
        cess="0",
        invoice_value="11800.00",
    )
    assert invoice.total_tax == Decimal("1800.00")


def test_report_summarizes_risk_by_status_and_supplier() -> None:
    result = MatchResult(
        status=MatchStatus.MISSING_IN_2B,
        books_invoice=Invoice(
            source=InvoiceSource.BOOKS,
            row_id="books-1",
            supplier_gstin="27AAAAA0000A1Z5",
            supplier_name="Example Supplier",
            invoice_number_raw="INV/001",
            invoice_number_norm="INV001",
            invoice_date=date(2026, 10, 1),
            taxable_value=Decimal("10000"),
            igst=Decimal("1800"),
            cgst=Decimal("0"),
            sgst=Decimal("0"),
            cess=Decimal("0"),
            invoice_value=Decimal("11800"),
        ),
        itc_at_risk=Decimal("1800"),
    )
    report = ReconciliationReport.from_results([result])
    assert report.counts == {"MISSING_IN_2B": 1}
    assert report.total_itc_at_risk == Decimal("1800")
    assert report.per_supplier_itc_at_risk["Example Supplier"] == Decimal("1800")


def test_settings_defaults_are_configurable() -> None:
    settings = ReconciliationSettings(amount_tolerance="0.50", max_edit_distance=1)
    assert settings.amount_tolerance == Decimal("0.50")
    assert settings.max_edit_distance == 1

"""Contract tests for deterministic, JSON-safe report serialization."""
import json
from datetime import date
from decimal import Decimal
from itcguard.models import Invoice, InvoiceSource, MatchResult, MatchStatus, ReconciliationReport
from itcguard.report import serialize_report

def _invoice():
    return Invoice(source=InvoiceSource.BOOKS, row_id="row-1", supplier_gstin="27AAAAA0000A1Z5", supplier_name="Example Supplier", invoice_number_raw="INV-1", invoice_number_norm="INV1", invoice_date=date(2026, 1, 2), taxable_value=Decimal("1000.00"), igst=Decimal("180.00"), cgst=Decimal("0"), sgst=Decimal("0"), cess=Decimal("0"), invoice_value=Decimal("1180.00"))

def test_report_serializes_decimal_date_enum_and_invoice_as_json_safe_values():
    report = ReconciliationReport.from_results([MatchResult(status=MatchStatus.AMOUNT_MISMATCH, books_invoice=_invoice(), itc_at_risk=Decimal("180.00"))])
    payload = serialize_report(report)
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert payload["counts"] == {"AMOUNT_MISMATCH": 1}
    assert payload["total_itc_at_risk"] == "180.00"
    assert payload["results"][0]["status"] == "AMOUNT_MISMATCH"
    assert payload["results"][0]["books_invoice"]["invoice_date"] == "2026-01-02"
    assert payload["results"][0]["books_invoice"]["invoice_number_raw"] == "INV-1"

def test_report_serialization_is_deterministic():
    report = ReconciliationReport.from_results([MatchResult(status=MatchStatus.MATCHED, books_invoice=_invoice())])
    assert serialize_report(report) == serialize_report(report)

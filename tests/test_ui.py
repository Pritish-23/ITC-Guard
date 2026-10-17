"""Offline behavioural coverage for the planned Streamlit presentation helpers."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from itcguard.ingest import ingest_invoices
from itcguard.matcher import reconcile
from itcguard.models import InvoiceSource, ReconciliationReport

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _fixture_report() -> ReconciliationReport:
    books = ingest_invoices(
        FIXTURES / "purchase_register.csv",
        FIXTURES / "mappings" / "purchase_register.json",
        InvoiceSource.BOOKS,
    )
    gstr2b = ingest_invoices(
        FIXTURES / "gstr2b.csv",
        FIXTURES / "mappings" / "gstr2b.json",
        InvoiceSource.GSTR2B,
    )
    return ReconciliationReport.from_results(
        reconcile(books, gstr2b),
        supplier_drafts={"Alpha Components": "Please review invoice ALPHA-004."},
    )


def _ui():
    return pytest.importorskip("itcguard.ui")


def _helper(module, *names):
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    pytest.skip(f"planned UI helper not exposed (tried {names!r})")


def _flatten(value):
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()} | {
            key: item for child in value.values() if isinstance(child, (dict, list, tuple))
            for key, item in _flatten(child).items()
        }
    if isinstance(value, (list, tuple)):
        return {key: item for child in value for key, item in _flatten(child).items()}
    return {}


def test_fixture_report_display_data_surfaces_risk_and_supplier_drafts():
    ui = _ui()
    report = _fixture_report()
    present = _helper(ui, "report_to_display_data", "build_display_data", "display_data_for_report")
    display = present(report)
    flat = _flatten(display)
    assert any(v in (Decimal("912.00"), "912.00", 912.0) for v in flat.values())
    assert any(v in (Decimal("3294.00"), "3294.00", 3294.0) for v in flat.values())
    assert any(v in (Decimal("4206.00"), "4206.00", 4206.0) for v in flat.values())
    assert "Please review invoice ALPHA-004." in repr(display)


def test_fixture_workflow_exposes_confirmed_potential_and_total_risk():
    report = _fixture_report()
    assert report.confirmed_itc_at_risk == Decimal("912.00")
    assert report.potential_itc_at_risk == Decimal("3294.00")
    assert report.total_itc_at_risk == Decimal("4206.00")
    assert report.supplier_drafts


def test_uploaded_csv_bytes_flow_is_reconciled_when_helper_is_exposed():
    ui = _ui()
    reconcile_upload = _helper(ui, "reconcile_uploaded_bytes", "reconcile_uploaded_files")
    books = (FIXTURES / "purchase_register.csv").read_bytes()
    gstr2b = (FIXTURES / "gstr2b.csv").read_bytes()
    try:
        result = reconcile_upload(books, gstr2b)
    except TypeError:
        result = reconcile_upload({"purchase_register.csv": books, "gstr2b.csv": gstr2b})
    report = result if isinstance(result, ReconciliationReport) else getattr(result, "report", result)
    assert report.confirmed_itc_at_risk == Decimal("912.00")
    assert report.potential_itc_at_risk == Decimal("3294.00")


def test_uploaded_json_bytes_flow_preserves_supplier_drafts_when_helper_is_exposed():
    ui = _ui()
    reconcile_upload = _helper(ui, "reconcile_uploaded_bytes", "reconcile_uploaded_files")
    csv_bytes = (FIXTURES / "purchase_register.csv").read_bytes()
    json_bytes = (FIXTURES / "gstr2b.json").read_bytes()
    try:
        result = reconcile_upload(csv_bytes, json_bytes)
    except TypeError:
        result = reconcile_upload({"purchase_register.csv": csv_bytes, "gstr2b.json": json_bytes})
    report = result if isinstance(result, ReconciliationReport) else getattr(result, "report", result)
    assert isinstance(report.supplier_drafts, dict)


def test_download_helpers_produce_complete_user_files():
    ui = _ui()
    report = _fixture_report()

    report_json = ui.report_json_bytes(report).decode("utf-8")
    assert '"total_itc_at_risk": "4206.00"' in report_json
    assert '"supplier_drafts"' in report_json

    invoice_csv = ui.invoice_review_csv_bytes(report).decode("utf-8")
    assert "supplier,invoice,finding,amount_to_review,note" in invoice_csv
    assert "Amounts differ" in invoice_csv

    messages = ui.supplier_messages_text(report).decode("utf-8")
    assert "Alpha Components" in messages
    assert "Please review invoice ALPHA-004." in messages

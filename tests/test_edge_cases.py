import json

import pytest

from itcguard.ingest import IngestionError, ingest_invoices, load_records
from itcguard.models import InvoiceSource


def _mapping(path):
    fields = (
        "supplier_gstin",
        "supplier_name",
        "invoice_number",
        "invoice_date",
        "taxable_value",
        "igst",
        "cgst",
        "sgst",
        "cess",
        "invoice_value",
    )
    path.write_text(
        json.dumps({"column_mapping": {field: field for field in fields}}),
        encoding="utf-8",
    )


def test_empty_json_list_is_a_valid_empty_input(tmp_path) -> None:
    data = tmp_path / "empty.json"
    mapping = tmp_path / "mapping.json"
    data.write_text("[]", encoding="utf-8")
    _mapping(mapping)

    assert load_records(data) == []
    assert ingest_invoices(data, mapping, InvoiceSource.BOOKS) == []


def test_empty_csv_without_header_is_rejected(tmp_path) -> None:
    data = tmp_path / "empty.csv"
    mapping = tmp_path / "mapping.json"
    data.write_text("", encoding="utf-8")
    _mapping(mapping)

    with pytest.raises(IngestionError, match="CSV has no header"):
        ingest_invoices(data, mapping, InvoiceSource.BOOKS)


def test_invalid_gstin_length_is_retained_and_warned(tmp_path) -> None:
    data = tmp_path / "invalid-gstin.json"
    mapping = tmp_path / "mapping.json"
    _mapping(mapping)
    data.write_text(
        json.dumps(
            [
                {
                    "supplier_gstin": "NOT-A-GSTIN",
                    "supplier_name": "Synthetic Supplier",
                    "invoice_number": "INV-1",
                    "invoice_date": "2026-04-05",
                    "taxable_value": "100.00",
                    "igst": "18.00",
                    "cgst": "0.00",
                    "sgst": "0.00",
                    "cess": "0.00",
                    "invoice_value": "118.00",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match="expected 15"):
        invoices = ingest_invoices(data, mapping, InvoiceSource.BOOKS)
    assert invoices[0].supplier_gstin == "NOT-A-GSTIN"

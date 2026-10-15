import csv
import json
from decimal import Decimal

import pytest

from itcguard.ingest import IngestionError, ingest_invoices, load_mapping, load_records
from itcguard.models import InvoiceSource


FIELDS = [
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
]


def _mapping(path, *, column_mapping=None) -> None:
    path.write_text(
        json.dumps({"column_mapping": column_mapping or {field: f"src_{field}" for field in FIELDS}}),
        encoding="utf-8",
    )


def _row() -> dict[str, str]:
    return {
        "src_supplier_gstin": " 27aaaaa1234a1z5 ",
        "src_supplier_name": "Supplier",
        "src_invoice_number": "FY24-25/0007",
        "src_invoice_date": "2026-04-05",
        "src_taxable_value": "₹ 1,23,456.00",
        "src_igst": "22,222.08",
        "src_cgst": "0",
        "src_sgst": "0",
        "src_cess": "0",
        "src_invoice_value": "1,45,678.08",
    }


def test_load_csv_and_json_records_and_build_typed_invoice(tmp_path) -> None:
    mapping = tmp_path / "mapping.json"
    _mapping(mapping)
    csv_path = tmp_path / "invoices.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row()))
        writer.writeheader()
        writer.writerow(_row())
    json_path = tmp_path / "invoices.json"
    json_path.write_text(json.dumps([_row()]), encoding="utf-8")

    assert len(load_records(csv_path)) == 1
    assert len(load_records(json_path)) == 1
    invoice = ingest_invoices(
        csv_path,
        mapping,
        InvoiceSource.BOOKS,
        financial_year_prefix="FY24-25",
    )[0]
    assert invoice.source is InvoiceSource.BOOKS
    assert invoice.row_id == "books-2"
    assert invoice.supplier_gstin == "27AAAAA1234A1Z5"
    assert invoice.invoice_number_norm == "7"
    assert invoice.taxable_value == Decimal("123456.00")


def test_missing_mapping_field_is_reported(tmp_path) -> None:
    mapping = tmp_path / "mapping.json"
    _mapping(mapping, column_mapping={"supplier_gstin": "GSTIN"})
    with pytest.raises(IngestionError, match="missing canonical field.*supplier_name"):
        load_mapping(mapping)


def test_missing_column_and_required_value_include_source_row_and_column(tmp_path) -> None:
    mapping = tmp_path / "mapping.json"
    _mapping(mapping)
    csv_path = tmp_path / "invoices.csv"
    row = _row()
    row.pop("src_invoice_value")
    header = list(_row())
    header.remove("src_invoice_value")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(IngestionError, match="source=.*column=.*src_invoice_value"):
        ingest_invoices(csv_path, mapping, "books")

    row = _row()
    row["src_invoice_number"] = ""
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row()))
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(IngestionError, match="row=2.*src_invoice_number.*missing required"):
        ingest_invoices(csv_path, mapping, "books")


def test_bad_amount_and_date_are_contextual_errors(tmp_path) -> None:
    mapping = tmp_path / "mapping.json"
    _mapping(mapping)
    json_path = tmp_path / "invoices.json"
    row = _row()
    row["src_igst"] = "not-money"
    json_path.write_text(json.dumps([row]), encoding="utf-8")
    with pytest.raises(IngestionError, match="source=.*row=1.*src_igst.*malformed"):
        ingest_invoices(json_path, mapping, "gstr2b")

    row["src_igst"] = "0"
    row["src_invoice_date"] = "05/04/2026"
    json_path.write_text(json.dumps([row]), encoding="utf-8")
    with pytest.raises(IngestionError, match="row=1.*src_invoice_date.*ambiguous"):
        ingest_invoices(json_path, mapping, "gstr2b")

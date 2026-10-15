import csv
import json
from pathlib import Path


FIXTURES = Path(__file__).parents[1] / "fixtures"
CANONICAL_FIELDS = {
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
}


def read_csv(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_synthetic_csvs_have_canonical_shape_and_expected_size() -> None:
    books = read_csv("purchase_register.csv")
    gstr2b = read_csv("gstr2b.csv")

    assert len(books) == 40
    assert len(gstr2b) == 40
    assert set(books[0]) == CANONICAL_FIELDS
    assert set(gstr2b[0]) == CANONICAL_FIELDS
    assert len({row["supplier_name"] for row in books}) == 6
    assert all(len(row["supplier_gstin"]) == 15 for row in books + gstr2b)


def test_json_fixture_matches_gstr2b_csv() -> None:
    csv_rows = read_csv("gstr2b.csv")
    json_rows = json.loads((FIXTURES / "gstr2b.json").read_text(encoding="utf-8"))
    assert json_rows == csv_rows


def test_mapping_examples_cover_every_canonical_field() -> None:
    for name in ("purchase_register.json", "gstr2b.json"):
        mapping = json.loads((FIXTURES / "mappings" / name).read_text(encoding="utf-8"))
        assert set(mapping["canonical_schema"]) == CANONICAL_FIELDS
        assert set(mapping["column_mapping"]) == CANONICAL_FIELDS

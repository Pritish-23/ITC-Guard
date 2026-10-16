import json
from pathlib import Path

from fastapi.testclient import TestClient

from itcguard.api import app


FIXTURES = Path(__file__).parents[1] / "fixtures"


client = TestClient(app)


def test_health_and_index_are_available() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}

    index = client.get("/")
    assert index.status_code == 200
    assert "ITC Guard" in index.text
    assert "/report" in index.text


def test_reconcile_endpoint_uses_same_report_as_cli() -> None:
    response = client.post("/reconcile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"] == {
        "MATCHED": 32,
        "AMOUNT_MISMATCH": 3,
        "MISSING_IN_2B": 1,
        "MISSING_IN_BOOKS": 2,
        "POSSIBLE_MATCH": 3,
        "DUPLICATE": 1,
    }
    assert payload["total_itc_at_risk"] == "4206.00"
    assert len(payload["supplier_drafts"]) == 3


def test_reconcile_accepts_relative_paths_and_report_is_readable() -> None:
    response = client.post(
        "/reconcile",
        json={
            "books": "fixtures/purchase_register.csv",
            "gstr2b": "fixtures/gstr2b.json",
            "mapping": "fixtures/mappings/gstr2b.json",
        },
    )
    assert response.status_code == 200
    assert response.json()["results"]

    report = client.get("/report")
    assert report.status_code == 200
    assert "Total ITC risk" in report.text
    assert "Fictional Alpha Industrial Supplies" in report.text
    assert "Supplier explanations" in report.text


def test_reconcile_rejects_missing_file_and_unknown_fields() -> None:
    missing = client.post("/reconcile", json={"books": "fixtures/nope.csv"})
    assert missing.status_code == 400
    assert "file not found" in missing.json()["detail"]

    unknown = client.post("/reconcile", json={"unexpected": "value"})
    assert unknown.status_code == 422

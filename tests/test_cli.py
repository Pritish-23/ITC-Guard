"""End-to-end checks for the supported ``itcguard reconcile`` command."""

import json
import sys
from pathlib import Path

from itcguard.cli import main

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures"

def _run_cli(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["itcguard", *map(str, args)])
    try:
        return main()
    except SystemExit as exc:
        return exc.code

def test_reconcile_fixture_succeeds_with_expected_counts_and_risk(monkeypatch, tmp_path, capsys):
    result = _run_cli(monkeypatch, "reconcile", "--books", FIXTURES / "purchase_register.csv", "--gstr2b", FIXTURES / "gstr2b.csv", "--mapping", FIXTURES / "mappings" / "purchase_register.json", "--out", tmp_path)
    assert result == 0
    assert "Traceback" not in capsys.readouterr().err
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["counts"] == {"MATCHED": 32, "AMOUNT_MISMATCH": 3, "MISSING_IN_2B": 1, "MISSING_IN_BOOKS": 2, "POSSIBLE_MATCH": 3, "DUPLICATE": 1}
    assert report["total_itc_at_risk"] == "4206.00"
    assert set(report["supplier_drafts"]) == {
        "Fictional Alpha Industrial Supplies",
        "Fictional Beta Circuitry Works",
        "Fictional Fable Logistics Lab",
    }
    assert list(tmp_path.iterdir())

def test_reconcile_missing_input_is_clean_nonzero_error(monkeypatch, tmp_path, capsys):
    result = _run_cli(monkeypatch, "reconcile", "--books", tmp_path / "missing.csv", "--gstr2b", FIXTURES / "gstr2b.csv", "--mapping", FIXTURES / "mappings" / "purchase_register.json", "--out", tmp_path / "out")
    captured = capsys.readouterr()
    assert result != 0
    assert "Traceback" not in captured.err
    assert "missing.csv" in captured.err

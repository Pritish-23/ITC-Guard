"""Command-line entry point for ITC Guard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agents.graph import invoke_offline
from .ingest import IngestionError, ingest_invoices
from .models import InvoiceSource, ReconciliationReport
from .report import write_report


def build_parser() -> argparse.ArgumentParser:
    """Build the reconciliation command parser."""
    parser = argparse.ArgumentParser(
        prog="itcguard",
        description="Reconcile a purchase register against a GSTR-2B export.",
    )
    subparsers = parser.add_subparsers(dest="command")
    reconcile_parser = subparsers.add_parser(
        "reconcile", help="reconcile books and GSTR-2B data"
    )
    reconcile_parser.add_argument("--books", required=True, help="purchase register path")
    reconcile_parser.add_argument("--gstr2b", required=True, help="GSTR-2B export path")
    reconcile_parser.add_argument("--mapping", required=True, help="column mapping path")
    reconcile_parser.add_argument("--out", help="directory for report files")
    return parser


def run_reconciliation(books_path: str, gstr2b_path: str, mapping_path: str) -> ReconciliationReport:
    """Ingest both sources and run the complete offline agent pipeline."""
    books = ingest_invoices(books_path, mapping_path, InvoiceSource.BOOKS)
    gstr2b = ingest_invoices(gstr2b_path, mapping_path, InvoiceSource.GSTR2B)
    state = invoke_offline({"books_invoices": books, "gstr2b_invoices": gstr2b})
    return state["report"]


def _print_summary(report: ReconciliationReport, report_path: Path) -> None:
    print("Reconciliation summary")
    print(f"  Results: {len(report.results)}")
    print("  Status counts:")
    for status, count in sorted(report.counts.items()):
        print(f"    {status}: {count}")
    print(f"  Total ITC at risk: ₹{report.total_itc_at_risk}")
    print("  ITC at risk by supplier:")
    for supplier, amount in sorted(report.per_supplier_itc_at_risk.items()):
        print(f"    {supplier}: ₹{amount}")
    print(f"  Report: {report_path}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command != "reconcile":
        parser.print_help()
        return 0
    try:
        report = run_reconciliation(args.books, args.gstr2b, args.mapping)
        report_path = write_report(report, args.out or ".")
    except (IngestionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_summary(report, report_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Command-line entry point for ITC Guard."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser before reconciliation commands are added."""
    parser = argparse.ArgumentParser(
        prog="itcguard",
        description="Reconcile a purchase register against a GSTR-2B export.",
    )
    subparsers = parser.add_subparsers(dest="command")
    reconcile = subparsers.add_parser(
        "reconcile",
        help="reconcile books and GSTR-2B data",
    )
    reconcile.add_argument("--books", required=True, help="purchase register path")
    reconcile.add_argument("--gstr2b", required=True, help="GSTR-2B export path")
    reconcile.add_argument("--mapping", required=True, help="column mapping path")
    reconcile.add_argument("--out", help="directory for report files")
    return parser


def main() -> int:
    """Parse arguments and report the current scaffold status."""
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "reconcile":
        parser.error("reconciliation is not implemented yet")
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

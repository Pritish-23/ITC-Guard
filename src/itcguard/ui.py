"""Local Streamlit front end for the ITC Guard reconciliation pipeline."""

from __future__ import annotations

import tempfile
import csv
import io
import json
from pathlib import Path
from typing import Any

import streamlit as st

from itcguard.cli import run_reconciliation
from itcguard.report import report_to_dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"

STATUS_LABELS = {
    "MATCHED": "Looks the same",
    "AMOUNT_MISMATCH": "Amounts differ",
    "MISSING_IN_2B": "Missing from tax statement",
    "MISSING_IN_BOOKS": "Missing from purchase list",
    "POSSIBLE_MATCH": "Needs a closer look",
    "DUPLICATE": "Repeated entry",
}


def report_to_display_data(report) -> dict[str, Any]:
    """Return the small, UI-friendly view model used by the Streamlit page."""

    return {
        "metrics": {
            "confirmed_itc_at_risk": str(report.confirmed_itc_at_risk),
            "potential_itc_at_risk": str(report.potential_itc_at_risk),
            "total_itc_at_risk": str(report.total_itc_at_risk),
        },
        "counts": dict(report.counts),
        "supplier_risk": {
            supplier: str(amount)
            for supplier, amount in report.per_supplier_itc_at_risk.items()
        },
        "supplier_drafts": dict(report.supplier_drafts),
        "results": [
            {
                "supplier": (result.books_invoice or result.gstr2b_invoice).supplier_name,
                "invoice": (result.books_invoice or result.gstr2b_invoice).invoice_number_raw,
                "status": result.status.value,
                "itc_at_risk": str(result.itc_at_risk),
                "explanation": result.explanation,
            }
            for result in report.results
            if result.books_invoice or result.gstr2b_invoice
        ],
    }


def report_json_bytes(report) -> bytes:
    """Return the complete report as a downloadable UTF-8 JSON file."""

    return (
        json.dumps(
            report_to_dict(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def invoice_review_csv_bytes(report) -> bytes:
    """Return a simple invoice review table for spreadsheet users."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=("supplier", "invoice", "finding", "amount_to_review", "note"),
    )
    writer.writeheader()
    for result in report.results:
        invoice = result.books_invoice or result.gstr2b_invoice
        if invoice is None:
            continue
        writer.writerow(
            {
                "supplier": invoice.supplier_name,
                "invoice": invoice.invoice_number_raw,
                "finding": STATUS_LABELS.get(result.status.value, result.status.value),
                "amount_to_review": str(result.itc_at_risk),
                "note": result.explanation,
            }
        )
    return output.getvalue().encode("utf-8")


def supplier_messages_text(report) -> bytes:
    """Return supplier follow-ups as a readable plain-text download."""

    sections = []
    for supplier, draft in report.supplier_drafts.items():
        sections.append(f"{supplier}\n{'=' * len(supplier)}\n{draft}")
    text = "\n\n".join(sections) if sections else "No supplier messages were generated."
    return (text + "\n").encode("utf-8")


def reconcile_uploaded_bytes(
    books_bytes: bytes,
    gstr2b_bytes: bytes,
    mapping_bytes: bytes | None = None,
    *,
    gstr2b_name: str = "gstr2b.csv",
):
    """Reconcile uploaded browser data through the existing pipeline."""

    gstr_suffix = Path(gstr2b_name).suffix.lower()
    if gstr_suffix == ".csv" and gstr2b_bytes.lstrip().startswith((b"[", b"{")):
        gstr_suffix = ".json"
    if gstr_suffix not in {".csv", ".json"}:
        raise ValueError("GSTR-2B upload must be a CSV or JSON file")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        books_path = root / "purchase_register.csv"
        gstr_path = root / f"gstr2b{gstr_suffix}"
        mapping_path = root / "mapping.json"
        books_path.write_bytes(books_bytes)
        gstr_path.write_bytes(gstr2b_bytes)
        if mapping_bytes is None:
            mapping_path = FIXTURES / "mappings" / "purchase_register.json"
        else:
            mapping_path.write_bytes(mapping_bytes)
        return run_reconciliation(str(books_path), str(gstr_path), str(mapping_path))


def _temporary_upload(uploaded_file, suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        handle.write(uploaded_file.getvalue())
    finally:
        handle.close()
    return Path(handle.name)

def _money(value) -> str:
    return f"₹{value:,.2f}"

def _show_report(report) -> None:
    st.header("Your results")
    columns = st.columns(3)
    columns[0].metric("Amount needing attention", _money(report.confirmed_itc_at_risk))
    columns[1].metric("Possible amount", _money(report.potential_itc_at_risk))
    columns[2].metric("Total flagged", _money(report.total_itc_at_risk))
    left, right = st.columns(2)
    with left:
        st.markdown("#### What we found")
        st.dataframe(
            {
                STATUS_LABELS.get(status, status): count
                for status, count in report.counts.items()
            },
            use_container_width=True,
        )
    with right:
        st.markdown("#### Amount by supplier")
        st.dataframe(
            {supplier: _money(amount) for supplier, amount in report.per_supplier_itc_at_risk.items()},
            use_container_width=True,
        )
    st.markdown("#### Invoice review")
    rows = []
    for result in report.results:
        invoice = result.books_invoice or result.gstr2b_invoice
        rows.append(
            {
                "Supplier": invoice.supplier_name if invoice else "Unknown",
                "Invoice": invoice.invoice_number_raw if invoice else "Unknown",
                "Finding": STATUS_LABELS.get(result.status.value, result.status.value),
                "Amount to review": _money(result.itc_at_risk),
                "Note": result.explanation,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.markdown("#### Messages for suppliers")
    if report.supplier_drafts:
        for supplier, draft in report.supplier_drafts.items():
            with st.expander(supplier):
                st.text(draft)
    else:
        st.info("No supplier messages were generated.")
    st.markdown("#### Download your results")
    download_columns = st.columns(3)
    download_columns[0].download_button(
        "Full report (JSON)",
        data=report_json_bytes(report),
        file_name="itc-guard-report.json",
        mime="application/json",
        use_container_width=True,
    )
    download_columns[1].download_button(
        "Invoice review (CSV)",
        data=invoice_review_csv_bytes(report),
        file_name="itc-guard-invoice-review.csv",
        mime="text/csv",
        use_container_width=True,
    )
    download_columns[2].download_button(
        "Supplier messages (TXT)",
        data=supplier_messages_text(report),
        file_name="itc-guard-supplier-messages.txt",
        mime="text/plain",
        use_container_width=True,
    )

def main() -> None:
    st.set_page_config(page_title="ITC Guard", page_icon="🧾", layout="wide")
    st.title("🧾 Check your purchase records")
    st.caption("Compare your purchase list with your tax statement and find items that need attention.")
    st.warning("Before using real files, check that their column names match. This tool helps with review; it is not tax or legal advice.")
    st.markdown("### How it works")
    st.markdown("1. Add your purchase list and tax statement.\n2. Click **Check my files**.\n3. Read the results and download the report or supplier messages.")
    with st.sidebar:
        st.header("Your files")
        books_upload = st.file_uploader("1. Purchase list (CSV)", type=["csv"])
        gstr_upload = st.file_uploader("2. Tax statement (CSV or JSON)", type=["csv", "json"])
        mapping_upload = st.file_uploader(
            "3. Column matching file (optional)",
            type=["json"],
            help="Only add this if your file headings are different from the sample headings.",
        )
        run = st.button(
            "Check my files" if books_upload or gstr_upload else "Try sample files",
            type="primary",
            use_container_width=True,
        )
    if run:
        temp_paths = []
        try:
            books = _temporary_upload(books_upload, ".csv") if books_upload else FIXTURES / "purchase_register.csv"
            gstr = _temporary_upload(gstr_upload, Path(gstr_upload.name).suffix) if gstr_upload else FIXTURES / "gstr2b.csv"
            mapping = _temporary_upload(mapping_upload, ".json") if mapping_upload else FIXTURES / "mappings" / "purchase_register.json"
            temp_paths = [path for path, upload in ((books, books_upload), (gstr, gstr_upload), (mapping, mapping_upload)) if upload]
            st.session_state["report"] = run_reconciliation(str(books), str(gstr), str(mapping))
        except Exception as exc:
            st.error(f"Could not reconcile these files: {exc}")
        finally:
            for path in temp_paths:
                path.unlink(missing_ok=True)
    if "report" in st.session_state:
        _show_report(st.session_state["report"])
    else:
        st.info("No files added yet. Click **Try sample files** to see how the tool works.")

if __name__ == "__main__":
    main()

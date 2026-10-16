"""Local Streamlit front end for the ITC Guard reconciliation pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from itcguard.cli import run_reconciliation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"


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
    st.subheader("Reconciliation summary")
    columns = st.columns(3)
    columns[0].metric("Confirmed exposure", _money(report.confirmed_itc_at_risk))
    columns[1].metric("Potential exposure", _money(report.potential_itc_at_risk))
    columns[2].metric("Total exposure", _money(report.total_itc_at_risk))
    left, right = st.columns(2)
    with left:
        st.markdown("#### Status counts")
        st.dataframe(report.counts, use_container_width=True)
    with right:
        st.markdown("#### Supplier risk")
        st.dataframe({k: _money(v) for k, v in report.per_supplier_itc_at_risk.items()}, use_container_width=True)
    st.markdown("#### Invoice explanations")
    rows = []
    for result in report.results:
        invoice = result.books_invoice or result.gstr2b_invoice
        rows.append({"Supplier": invoice.supplier_name if invoice else "Unknown", "Invoice": invoice.invoice_number_raw if invoice else "Unknown", "Status": result.status.value, "ITC at risk": _money(result.itc_at_risk), "Explanation": result.explanation})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.markdown("#### Grouped supplier drafts")
    if report.supplier_drafts:
        for supplier, draft in report.supplier_drafts.items():
            with st.expander(supplier):
                st.text(draft)
    else:
        st.info("No supplier drafts were generated for this reconciliation.")

def main() -> None:
    st.set_page_config(page_title="ITC Guard", page_icon="🧾", layout="wide")
    st.title("🧾 ITC Guard")
    st.caption("Offline purchase-register and GSTR-2B reconciliation")
    st.warning("GSTR-2B column mappings must be verified before use. Outputs are for review only and are not tax advice.")
    st.info("Upload your own files in the sidebar, or run the bundled synthetic demo without uploading anything.")
    with st.sidebar:
        st.header("Inputs")
        books_upload = st.file_uploader("Purchase register CSV", type=["csv"])
        gstr_upload = st.file_uploader("GSTR-2B CSV or JSON", type=["csv", "json"])
        mapping_upload = st.file_uploader("Optional mapping JSON", type=["json"])
        run = st.button("Run reconciliation", type="primary", use_container_width=True)
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
        st.info("Bundled fixture demo is selected by default. Click Run reconciliation to begin.")

if __name__ == "__main__":
    main()

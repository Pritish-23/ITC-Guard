"""FastAPI HTTP surface for the offline ITC Guard reconciliation flow."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from .cli import run_reconciliation
from .ingest import IngestionError
from .report import report_to_dict

app = FastAPI(title="ITC Guard", version="0.1.0")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ReconcilePayload(BaseModel):
    """Optional input paths; omitted values select the checked-in fixtures."""

    model_config = ConfigDict(extra="forbid")
    books: str | None = None
    gstr2b: str | None = None
    mapping: str | None = None


def _fixture(name: str) -> Path:
    return _PROJECT_ROOT / "fixtures" / name


def _path(value: str | None, default: Path, label: str) -> Path:
    path = Path(value) if value else default
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"{label} file not found: {value or default}")
    return path


def reconcile_payload(payload: ReconcilePayload | dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the same deterministic agent pipeline as the CLI and return JSON data."""
    if payload is None:
        request = ReconcilePayload()
    elif isinstance(payload, ReconcilePayload):
        request = payload
    else:
        try:
            request = ReconcilePayload.model_validate(payload)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    books = _path(request.books, _fixture("purchase_register.csv"), "books")
    gstr2b = _path(request.gstr2b, _fixture("gstr2b.csv"), "gstr2b")
    mapping = _path(request.mapping, _fixture("mappings/purchase_register.json"), "mapping")
    try:
        return report_to_dict(run_reconciliation(str(books), str(gstr2b), str(mapping)))
    except (IngestionError, OSError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html><html><head><title>ITC Guard</title></head><body>
<h1>ITC Guard</h1><p>Offline purchase-register and GSTR-2B reconciliation.</p>
<p><a href=\"/report\">View bundled demo report</a></p>
<form method=\"post\" action=\"/reconcile\"><button type=\"submit\">Run bundled demo</button></form>
</body></html>"""


@app.post("/reconcile")
def reconcile_endpoint(payload: ReconcilePayload | None = None) -> dict[str, Any]:
    return reconcile_payload(payload)


def _report_html(data: dict[str, Any]) -> str:
    def money(value: Any) -> str:
        return f"₹{escape(str(value if value is not None else '0.00'))}"
    counts = data.get("counts") or {}
    results = data.get("results") or []
    matched = data.get("matched_count", data.get("matched", counts.get("MATCHED", 0)))
    confirmed = data.get("confirmed_itc_risk", data.get("confirmed_itc_at_risk", data.get("total_itc_at_risk", "0.00")))
    potential = data.get("potential_itc_risk", data.get("potential_itc_at_risk", "0.00"))
    exposure = data.get("total_exposure", data.get("total_itc_at_risk", confirmed))
    cards = "".join(f'<div class="card"><span>{label}</span><strong>{value}</strong></div>' for label, value in (("Matched", matched), ("Confirmed ITC risk", money(confirmed)), ("Potential ITC risk", money(potential)), ("Total exposure", money(exposure))))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        inv = result.get("books_invoice") or result.get("gstr2b_invoice") or {}
        grouped.setdefault(str(inv.get("supplier_name", "Unknown supplier")), []).append(result)
    sections = []
    for supplier_name, supplier_results in grouped.items():
        rows = []
        for result in supplier_results:
            inv = result.get("books_invoice") or result.get("gstr2b_invoice") or {}
            status = str(result.get("status", "UNKNOWN"))
            invoice = inv.get("invoice_number_raw") or inv.get("invoice_number_norm") or "Invoice"
            rows.append(f'<li><span class="chip {escape(status.lower())}">{escape(status)}</span> <strong>{escape(str(invoice))}</strong> — {escape(str(result.get("explanation") or "No explanation provided."))}</li>')
        sections.append(f'<section class="supplier"><h3>{escape(supplier_name)}</h3><ul>{"".join(rows)}</ul></section>')
    suppliers = "".join(f"<li><strong>{escape(str(k))}</strong>: {money(v)}</li>" for k, v in (data.get("per_supplier_itc_at_risk") or {}).items()) or "<li>None</li>"
    drafts = "".join(f'<section class="draft"><h3>{escape(str(k))}</h3><pre>{escape(str(v))}</pre></section>' for k, v in (data.get("supplier_drafts") or {}).items())
    style = "<style>body{font:16px system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#172033;background:#f6f8fb}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:1.5rem 0}.card,.supplier,.draft{background:white;border:1px solid #dfe5ee;border-radius:10px;padding:1rem;box-shadow:0 2px 7px #17203312}.card span{display:block;color:#667085;font-size:.85rem}.card strong{display:block;font-size:1.45rem;margin-top:.35rem}.supplier{margin:.75rem 0}.chip{display:inline-block;border-radius:999px;padding:.2rem .55rem;font-size:.72rem;font-weight:700;background:#e5e7eb;color:#374151}.matched{background:#dcfce7;color:#166534}.amount_mismatch,.duplicate{background:#fef3c7;color:#92400e}.missing_in_2b,.missing_in_books{background:#fee2e2;color:#991b1b}.possible_match{background:#dbeafe;color:#1e40af}li{margin:.6rem 0}p{line-height:1.5}pre{white-space:pre-wrap;font:inherit;line-height:1.5;margin:0}</style>"
    count_html = "".join(f'<li>{escape(str(k))}: {escape(str(v))}</li>' for k, v in counts.items())
    return f'<!doctype html><html><head><meta charset="utf-8"><title>ITC Guard report</title>{style}</head><body><h1>ITC Guard reconciliation report</h1><p>Review matched invoices, confirmed exposure, and supplier follow-ups.</p><div class="cards">{cards}</div><h2>Status counts</h2><ul>{count_html}</ul><h2>ITC risk by supplier</h2><ul>{suppliers}</ul><h2>Supplier explanations</h2>{"".join(sections) or "<p>No reconciliation results.</p>"}<h2>Drafts</h2>{drafts or "<p>No drafts.</p>"}</body></html>'


@app.get("/report", response_class=HTMLResponse)
def report() -> HTMLResponse:
    try:
        return HTMLResponse(_report_html(reconcile_payload()))
    except HTTPException:
        raise

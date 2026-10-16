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
    counts = "".join(f"<li>{escape(str(k))}: {v}</li>" for k, v in data["counts"].items())
    suppliers = "".join(f"<li>{escape(str(k))}: ₹{escape(str(v))}</li>" for k, v in data["per_supplier_itc_at_risk"].items()) or "<li>None</li>"
    sections = []
    for result in data["results"]:
        inv = result.get("books_invoice") or result.get("gstr2b_invoice") or {}
        supplier = escape(str(inv.get("supplier_name", "Unknown supplier")))
        explanation = escape(str(result.get("explanation") or "No explanation provided."))
        sections.append(f"<section><h3>{supplier}</h3><p>Status: <strong>{escape(str(result.get('status')))}</strong></p><p>Explanation: {explanation}</p></section>")
    drafts = "".join(f"<section><h3>{escape(str(k))}</h3><p>{escape(str(v))}</p></section>" for k, v in data["supplier_drafts"].items())
    return f"<!doctype html><html><head><title>ITC Guard report</title></head><body><h1>ITC Guard reconciliation report</h1><h2>Status counts</h2><ul>{counts}</ul><h2>Total ITC risk</h2><p>₹{escape(str(data['total_itc_at_risk']))}</p><h2>ITC risk by supplier</h2><ul>{suppliers}</ul><h2>Supplier explanations</h2>{''.join(sections)}<h2>Drafts</h2>{drafts or '<p>No drafts.</p>'}</body></html>"""


@app.get("/report", response_class=HTMLResponse)
def report() -> HTMLResponse:
    try:
        return HTMLResponse(_report_html(reconcile_payload()))
    except HTTPException:
        raise

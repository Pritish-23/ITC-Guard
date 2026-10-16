"""Deterministic grounding and safety review for explanations and drafts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..llm.base import LLMProvider
from .drafter import _fallback, _fields
from .state import GraphState

_PROMPT = (Path(__file__).parent / "prompts" / "reviewer_v1.txt").read_text(encoding="utf-8")
_ADVICE = re.compile(
    r"\b(?:must|should|liable|claim|eligible|ineligible|deduct|penalty|compliance|legal advice|tax advice)\b",
    re.IGNORECASE,
)
_GSTIN = re.compile(r"\b[A-Z0-9]{15}\b", re.IGNORECASE)
_DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b")
_RUPEE = re.compile(r"₹\s*[0-9][0-9,]*(?:\.[0-9]+)?")
_INVOICE_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-_/\.][A-Z0-9]+)+\b", re.IGNORECASE)
_SAFE_TOKENS = {"GSTR-2B", "ITC-2B"}


def _known_values(invoices: list[Any]) -> set[str]:
    values: set[str] = set()
    for invoice in invoices:
        values.update(
            {
                invoice.invoice_number_raw,
                invoice.invoice_number_norm,
                invoice.supplier_gstin,
                invoice.invoice_date.isoformat(),
                invoice.invoice_date.strftime("%d-%m-%Y"),
                invoice.invoice_date.strftime("%d/%m/%Y"),
                str(invoice.taxable_value),
                str(invoice.igst),
                str(invoice.cgst),
                str(invoice.sgst),
                str(invoice.cess),
                str(invoice.total_tax),
                str(invoice.invoice_value),
            }
        )
    return values


def _amount_is_known(token: str, known: set[str]) -> bool:
    plain = token.replace("₹", "").replace(",", "").replace(" ", "")
    return plain in known or any(value.replace(",", "") == plain for value in known)


def validate_grounded_text(text: str, invoices: list[Any]) -> tuple[bool, str | None]:
    """Validate data references and reject advice-like language."""

    if _ADVICE.search(text):
        return False, "advice-like wording"
    known = _known_values(invoices)
    for token in _GSTIN.findall(text):
        if token.upper() not in {value.upper() for value in known}:
            return False, f"unknown GSTIN {token}"
    for token in _DATE.findall(text):
        if token not in known:
            return False, f"unknown date {token}"
    for token in _RUPEE.findall(text):
        if not _amount_is_known(token, known):
            return False, f"unknown amount {token}"
    for token in _INVOICE_TOKEN.findall(text):
        if token.upper() in _SAFE_TOKENS:
            continue
        if any(char.isdigit() for char in token) and token.upper() not in {
            value.upper() for value in known
        }:
            return False, f"unknown invoice reference {token}"
    return True, None


def _supplier_invoices(state: GraphState) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for result in state.get("match_results", []):
        for invoice in (result.books_invoice, result.gstr2b_invoice):
            if invoice is not None and invoice not in grouped.setdefault(invoice.supplier_name, []):
                grouped[invoice.supplier_name].append(invoice)
    return grouped


def review_drafts(state: GraphState, provider: LLMProvider | None = None) -> GraphState:
    drafts = dict(state.get("drafts", {}))
    explanations = dict(state.get("explanations", {}))
    metadata = dict(state.get("review", {}))
    comments = list(metadata.get("comments", []))
    grouped = _supplier_invoices(state)

    # Explanations are also user-visible generated text and receive the same
    # deterministic guardrail before they are included in the report.
    for result in state.get("match_results", []):
        invoice = result.books_invoice or result.gstr2b_invoice
        if invoice is None or not result.explanation:
            continue
        supplier_invoices = grouped.get(invoice.supplier_name, [])
        valid, reason = validate_grounded_text(result.explanation, supplier_invoices)
        if not valid:
            result.explanation = "The source records require review; no additional conclusion was generated."
            explanations[invoice.row_id] = result.explanation
            comments.append(f"{invoice.supplier_name}: explanation replaced ({reason})")

    for supplier, text in list(drafts.items()):
        invoices = grouped.get(supplier, [])
        valid, reason = validate_grounded_text(text, invoices)
        if not valid and provider is not None:
            response = provider.structured_completion(
                _PROMPT + "\nDRAFT:\n" + text + "\nSOURCE:\n" + repr([_fields(i) for i in invoices]),
                output_schema={"draft": "string"},
            )
            data = response.get("structured", response.get("content", {}))
            candidate = data.get("draft", "") if isinstance(data, dict) else ""
            valid, reason = validate_grounded_text(str(candidate), invoices)
            if valid:
                drafts[supplier] = str(candidate)
        if not valid:
            issues = [
                (str(index), result)
                for index, result in enumerate(state.get("match_results", []))
                if (result.books_invoice or result.gstr2b_invoice)
                and (result.books_invoice or result.gstr2b_invoice).supplier_name == supplier
            ]
            drafts[supplier] = _fallback(supplier, issues)
            comments.append(f"{supplier}: draft replaced by grounded safe template ({reason})")

    metadata["approved"] = not comments
    metadata["comments"] = comments
    metadata["requires_human_confirmation"] = bool(comments)
    state["drafts"] = drafts
    state["explanations"] = explanations
    state["review"] = metadata
    return state


def reviewer(state: GraphState, provider: LLMProvider | None = None) -> GraphState:
    return review_drafts(state, provider)


__all__ = ["review_drafts", "reviewer", "validate_grounded_text"]

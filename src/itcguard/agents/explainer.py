"""Grounded explanations for reconciliation mismatches."""

from __future__ import annotations

from pathlib import Path

from ..llm.base import LLMProvider
from ..models import MatchStatus
from .state import GraphState

_PROMPT = (Path(__file__).parent / "prompts" / "explainer_v1.txt").read_text(encoding="utf-8")


def _sentence(result) -> str:
    left, right = result.books_invoice, result.gstr2b_invoice
    if result.status is MatchStatus.AMOUNT_MISMATCH and left and right:
        return (
            f"Invoice {left.invoice_number_raw} for supplier {left.supplier_name} "
            f"has invoice values ₹{left.invoice_value} in the books and "
            f"₹{right.invoice_value} in GSTR-2B."
        )
    if result.status is MatchStatus.MISSING_IN_2B and left:
        return (
            f"Invoice {left.invoice_number_raw} for supplier {left.supplier_name} "
            "is present in the books but is not present in GSTR-2B."
        )
    if result.status is MatchStatus.MISSING_IN_BOOKS and right:
        return (
            f"Invoice {right.invoice_number_raw} for supplier {right.supplier_name} "
            "is present in GSTR-2B but is not present in the books."
        )
    if result.status is MatchStatus.DUPLICATE and (left or right):
        invoice = left or right
        return f"Invoice {invoice.invoice_number_raw} for supplier {invoice.supplier_name} appears more than once in its source."
    if result.status is MatchStatus.POSSIBLE_MATCH and left and right:
        return (
            f"Books invoice {left.invoice_number_raw} and GSTR-2B invoice "
            f"{right.invoice_number_raw} share supplier and amount details but need review."
        )
    return "The invoice records require review because the source records do not establish a confirmed match."


def explain_mismatches(
    state: GraphState,
    provider: LLMProvider | None = None,
) -> GraphState:
    explanations = dict(state.get("explanations", {}))
    for result in state.get("match_results", []):
        if result.status is MatchStatus.MATCHED:
            continue
        invoice = result.books_invoice or result.gstr2b_invoice
        key = invoice.row_id if invoice else str(len(explanations))
        if provider is not None:
            provider.structured_completion(
                _PROMPT + "\nSTATUS:\n" + result.status.value,
                output_schema={"explanation": "string"},
            )
        explanations[key] = _sentence(result)
        result.explanation = explanations[key]
    state["explanations"] = explanations
    return state


def explainer(state: GraphState, provider: LLMProvider | None = None) -> GraphState:
    return explain_mismatches(state, provider)


__all__ = ["explain_mismatches", "explainer"]

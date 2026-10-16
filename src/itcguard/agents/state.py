"""Typed state passed between reconciliation graph nodes."""

from __future__ import annotations

from typing import Any, TypedDict

from ..models import Invoice, MatchResult, ReconciliationReport
from ..settings import ReconciliationSettings


class ReviewMetadata(TypedDict, total=False):
    approved: bool
    reviewer: str
    comments: list[str]
    requires_human_confirmation: bool


class GraphState(TypedDict, total=False):
    books_invoices: list[Invoice]
    gstr2b_invoices: list[Invoice]
    match_results: list[MatchResult]
    explanations: dict[str, str]
    drafts: dict[str, str]
    review: ReviewMetadata
    report: ReconciliationReport
    settings: ReconciliationSettings
    metadata: dict[str, Any]


__all__ = ["GraphState", "ReviewMetadata"]
